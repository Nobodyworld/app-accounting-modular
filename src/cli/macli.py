"""Command line interface for Modular Accounting automation and diagnostics."""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import sys
import tomllib
from collections.abc import Iterable, Sequence
from datetime import date
from pathlib import Path
from typing import Any, cast

import click
from apps.api.config import settings
from apps.api.db import engine, init_db
from apps.api.models.models import Account, AccountType
from apps.api.services.extension_loader import (
    ExtensionStatus,
    active_extensions,
    load_configured_extensions,
    registered_contracts,
)
from apps.api.services.fx_service import FXService
from apps.api.services.health import register_default_health_checks as _register_health_checks
from apps.api.services.ledger_service import LedgerService
from apps.api.services.market_service import MarketService
from apps.api.services.plugin_loader import load_provider
from apps.api.services.snapshot_service import SnapshotOrchestrator, scenario_batch_to_payload
from apps.extensions.scaffold import scaffold_extension
from apps.modular_accounting.application import SnapshotScenario
from apps.observability.diagnostics import collect_observability_snapshot
from apps.observability.health import health_registry
from apps.observability.logging import configure_logging, logging_context
from apps.observability.tracing import configure_tracing, traced
from sqlmodel import Session, select


def _bootstrap_observability() -> None:
    """Initialise logging and tracing for CLI invocations."""

    configure_logging(
        settings.log_level,
        settings.log_format,
        service_name="modular-accounting-cli",
        force=True,
        integrate_uvicorn=False,
    )
    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        try:
            stream_handler = cast(Any, handler)
            if hasattr(stream_handler, "stream"):
                stream_handler.stream = sys.stderr
        except AttributeError:
            continue
    logging.getLogger("apps.observability.tracing").setLevel(logging.WARNING)
    configure_tracing(
        service_name="modular-accounting-cli",
        exporter=settings.tracing_exporter,
        endpoint=settings.tracing_otlp_endpoint,
    )


def _render_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """Render ``rows`` as an aligned ASCII table."""

    widths = [len(header) for header in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(cell))

    def _format_row(values: Sequence[str]) -> str:
        return "  ".join(value.ljust(widths[idx]) for idx, value in enumerate(values))

    rendered = [_format_row(headers)]
    rendered.append("  ".join("-" * width for width in widths))
    rendered.extend(_format_row(row) for row in rows)
    return "\n".join(rendered)


def _extension_rows(statuses: Iterable[ExtensionStatus]) -> list[list[str]]:
    rows: list[list[str]] = []
    for status in statuses:
        manifest = status.manifest
        capabilities: str
        if manifest and manifest.capabilities:
            capabilities = ", ".join(manifest.capabilities)
        else:
            capabilities = "-"
        rows.append(
            [
                status.key,
                status.module,
                "yes" if status.enabled else "no",
                "yes" if manifest is not None else "no",
                manifest.name if manifest else "-",
                manifest.version if manifest else "-",
                capabilities,
            ]
        )
    return rows


def _extension_json(statuses: Iterable[ExtensionStatus]) -> list[dict[str, str]]:
    payload: list[dict[str, str]] = []
    for status in statuses:
        manifest = status.manifest
        capabilities = ", ".join(manifest.capabilities) if manifest and manifest.capabilities else "-"
        payload.append(
            {
                "Key": status.key,
                "Module": status.module,
                "Enabled": "yes" if status.enabled else "no",
                "Loaded": "yes" if manifest is not None else "no",
                "Name": manifest.name if manifest else "-",
                "Version": manifest.version if manifest else "-",
                "Capabilities": capabilities,
            }
        )
    return payload


def _ensure_extensions_loaded() -> Sequence[ExtensionStatus]:
    """Load configured extensions and return their status objects."""

    load_configured_extensions()
    return tuple(active_extensions())


def _json_dump(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=False)


def _register_default_health_checks() -> None:
    _register_health_checks()


def _parse_amount(value: str | None) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _load_transactions_from_csv(ledger: LedgerService, file_path: str | Path) -> list[dict[str, object]]:
    """Parse a CSV file into validated transaction payloads.

    Unknown accounts are created using provided metadata. Raises ``ClickException``
    for unbalanced transactions to prevent partial imports.
    """

    path = Path(file_path)
    if not path.exists():
        raise click.ClickException(f"CSV file not found: {path}")

    grouped: dict[tuple[date, str], list[dict[str, object]]] = {}

    with path.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                txn_date = date.fromisoformat((row.get("date") or "").strip())
            except ValueError as exc:
                raise click.ClickException(f"Invalid date in row: {row.get('date')}") from exc
            description = (row.get("description") or "").strip()
            if not description:
                raise click.ClickException("Description is required for each row")
            account_code = (row.get("account_code") or "").strip()
            if not account_code:
                raise click.ClickException("Account code is required for each row")
            account_name = (row.get("account_name") or account_code).strip()
            account_type = (row.get("account_type") or "ASSET").strip() or "ASSET"
            currency = (row.get("currency") or "USD").strip() or "USD"
            debit = _parse_amount(row.get("debit"))
            credit = _parse_amount(row.get("credit"))

            try:
                account = ledger.require_account(account_code)
            except ValueError:
                account = ledger.create_account(
                    name=account_name,
                    type=AccountType(account_type) if account_type else AccountType.ASSET,
                    code=account_code,
                    currency=currency,
                )
            key = (txn_date, description)
            postings = grouped.setdefault(key, [])
            postings.append(
                {
                    "account_id": account.id,
                    "debit": debit,
                    "credit": credit,
                    "currency": currency,
                }
            )

    transactions: list[dict[str, object]] = []
    for (txn_date, description), postings in grouped.items():
        total_debit = sum(float(cast(Any, p["debit"])) for p in postings)
        total_credit = sum(float(cast(Any, p["credit"])) for p in postings)
        if round(total_debit - total_credit, 4) != 0:
            raise click.ClickException(
                f"Unbalanced transaction '{description}' on {txn_date}: "
                f"debits={total_debit:.2f} credits={total_credit:.2f}"
            )
        transactions.append({"date": txn_date, "description": description, "postings": postings})

    return transactions


@click.group()
def cli() -> None:
    """Modular Accounting CLI."""

    _bootstrap_observability()


@cli.command("inspect-extensions")
@click.option(
    "--format",
    "format_",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    help="Output format (table or json).",
)
def inspect_extensions(format_: str) -> None:
    """List configured extensions and their load status."""

    with logging_context(command="inspect-extensions"):
        with traced("cli.inspect_extensions", format=format_):
            statuses: Sequence[ExtensionStatus] = ()
            try:
                statuses = _ensure_extensions_loaded()
            except Exception as exc:  # pragma: no cover - defensive guard
                click.echo(f"Failed to load extensions: {exc}", err=True)
                raise SystemExit(1) from exc

            if not statuses:
                click.echo("No extensions configured.")
                return

            if format_.lower() == "json":
                click.echo(_json_dump(_extension_json(statuses)))
                return

            headers = ("Key", "Module", "Enabled", "Loaded", "Name", "Version", "Capabilities")
            click.echo(_render_table(headers, _extension_rows(statuses)))


@cli.command("inspect-contracts")
@click.option(
    "--format",
    "format_",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    help="Output format (table or json).",
)
def inspect_contracts(format_: str) -> None:
    """Show extension-published automation contracts."""

    with logging_context(command="inspect-contracts"):
        with traced("cli.inspect_contracts", format=format_):
            try:
                _ensure_extensions_loaded()
            except Exception as exc:  # pragma: no cover - defensive guard
                click.echo(f"Failed to load extensions: {exc}", err=True)
                raise SystemExit(1) from exc

            contracts = registered_contracts()
            if not contracts:
                click.echo("No contracts registered.")
                return

            if format_.lower() == "json":
                grouped: dict[str, dict[str, Any]] = {}
                for status, contract in contracts:
                    entry = grouped.setdefault(
                        status.key,
                        {
                            "key": status.key,
                            "module": status.module,
                            "enabled": status.enabled,
                            "loaded": status.manifest is not None,
                            "contracts": [],
                        },
                    )
                    entry["contracts"].append(contract.serialise())
                click.echo(_json_dump(list(grouped.values())))
                return

            headers = ("Key", "Contract", "Kind", "Version", "Entry point")
            rows: list[list[str]] = []
            for status, contract in contracts:
                rows.append(
                    [
                        status.key,
                        contract.name,
                        contract.kind,
                        contract.version,
                        contract.entrypoint or "-",
                    ]
                )
            click.echo(_render_table(headers, rows))


@cli.command("health")
@click.option(
    "--format",
    "format_",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    help="Output format (table or json).",
)
def health_command(format_: str) -> None:
    """Execute health checks and report readiness status."""

    with logging_context(command="health"):
        with traced("cli.health", format=format_):
            _register_default_health_checks()
            reports = asyncio.run(health_registry.evaluate())

            critical_failures = [report for report in reports if not report.healthy and report.severity == "critical"]
            overall = "ok" if not critical_failures else "degraded"

            if format_.lower() == "json":
                payload = {
                    "status": overall,
                    "reports": [
                        {
                            "name": report.name,
                            "healthy": report.healthy,
                            "severity": report.severity,
                            "details": report.details,
                        }
                        for report in reports
                    ],
                }
                click.echo(_json_dump(payload))
            else:
                headers = ("Name", "Healthy", "Severity", "Details")
                rows = [
                    [
                        report.name,
                        "yes" if report.healthy else "no",
                        report.severity,
                        json.dumps(report.details, sort_keys=True) if report.details else "{}",
                    ]
                    for report in reports
                ]
                click.echo(_render_table(headers, rows))
                click.echo(f"Overall status: {overall}")

            raise SystemExit(0 if overall == "ok" else 1)


@cli.command("observe")
@click.option(
    "--format",
    "format_",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    help="Output format (table or json).",
)
def observe(format_: str) -> None:
    """Emit an aggregated observability snapshot."""

    with logging_context(command="observe"):
        with traced("cli.observe", format=format_):
            _register_default_health_checks()
            statuses = _ensure_extensions_loaded()
            snapshot = asyncio.run(collect_observability_snapshot(extension_status_provider=lambda: statuses))

            if format_.lower() == "json":
                click.echo(json.dumps(snapshot.as_dict()), nl=False)
                return

            metrics = snapshot.metrics
            headers = ("Metric", "Value")
            metric_rows = [
                ["metrics_lines", str(metrics.get("lines", 0))],
                ["metrics_bytes", str(metrics.get("bytes", 0))],
                ["registered_checks", ", ".join(metrics.get("checks", [])) or "-"],
                ["tracing_enabled", str(snapshot.tracing.get("enabled", False))],
                ["otel_enabled", str(snapshot.tracing.get("otel_enabled", False))],
                ["exporter", snapshot.tracing.get("exporter", "-")],
            ]
            click.echo("Observability snapshot")
            click.echo(_render_table(headers, metric_rows))

            if snapshot.incidents:
                click.echo("\nOpen incidents")
                incident_headers = ("Name", "Severity", "Action")
                incident_rows = [
                    [incident["name"], incident["severity"], incident.get("action", "-")]
                    for incident in snapshot.incidents
                ]
                click.echo(_render_table(incident_headers, incident_rows))
            else:
                click.echo("\nOpen incidents\nNone")

            if statuses:
                click.echo("\nExtensions")
                click.echo(
                    _render_table(
                        ("Key", "Module", "Enabled", "Loaded"),
                        [
                            [
                                status.key,
                                status.module,
                                "yes" if status.enabled else "no",
                                "yes" if status.manifest is not None else "no",
                            ]
                            for status in statuses
                        ],
                    )
                )


@cli.command("sync-fx")
@click.option("--base", default="USD")
@click.option("--provider", default="plugins.fx_ecb.provider")
def sync_fx(base: str, provider: str) -> None:
    """Synchronise FX rates using the configured provider."""

    with logging_context(command="sync-fx", base=base, provider=provider):
        with traced("cli.sync_fx", base=base, provider=provider):
            init_db()
            provider_handle = load_provider(provider)
            provider_instance = provider_handle.instance
            with Session(engine) as session:
                service = FXService(session, provider_instance)
                count = service.sync(base=base)
                click.echo(f"Synced {count} FX rates via {provider_handle.metadata.name}")


@cli.command("sync-prices")
@click.argument("symbol")
@click.option("--start", required=True)
@click.option("--end", required=True)
@click.option("--provider", default="plugins.market_yfinance.provider")
def sync_prices(symbol: str, start: str, end: str, provider: str) -> None:
    """Synchronise market prices for ``symbol`` between ``start`` and ``end`` dates."""

    with logging_context(command="sync-prices", symbol=symbol, provider=provider):
        with traced("cli.sync_prices", symbol=symbol, provider=provider):
            init_db()
            provider_handle = load_provider(provider)
            provider_instance = provider_handle.instance
            start_date = date.fromisoformat(start)
            end_date = date.fromisoformat(end)
            with Session(engine) as session:
                service = MarketService(session, provider_instance)
                count = service.sync_prices(symbol, start_date, end_date)
                click.echo(
                    f"Synced {count} prices for {symbol} from {start_date} to {end_date} "
                    f"via {provider_handle.metadata.name}"
                )


@cli.command("snapshot")
@click.option("--base", "base_currency", default="USD", show_default=True)
@click.option("--commodity", "commodity_symbols", multiple=True, default=(), help="Commodity symbols to include")
@click.option("--jurisdiction", "jurisdictions", multiple=True, help="Jurisdictions to include")
@click.option(
    "--format",
    "format_",
    type=click.Choice(["json", "table"], case_sensitive=False),
    default="json",
    show_default=True,
)
def snapshot_command(
    base_currency: str,
    commodity_symbols: tuple[str, ...],
    jurisdictions: tuple[str, ...],
    format_: str,
) -> None:
    """Generate a data snapshot using configured providers."""

    orchestrator = SnapshotOrchestrator()
    result = orchestrator.build_snapshot(
        base_currency=base_currency,
        commodity_symbols=commodity_symbols or None,
        jurisdictions=jurisdictions or None,
    )

    if format_.lower() == "json":
        click.echo(json.dumps(result.as_payload(), default=str))
        return

    payload = cast(dict[str, Any], result.as_payload())
    click.echo("Snapshot")
    click.echo(
        _render_table(
            ("Section", "Count"),
            [("fx_rates", str(len(payload["fx_rates"]))), ("tax_rules", str(len(payload["tax_rules"])))],
        )
    )
    click.echo("\nProviders:")
    click.echo(_json_dump(payload["providers"]))
    click.echo("\nDiagnostics")
    click.echo(_json_dump(payload["diagnostics"]))


@cli.command("snapshot-scenarios")
@click.option("--plan", required=True, type=click.Path(exists=True))
@click.option(
    "--format",
    "format_",
    type=click.Choice(["json", "table"], case_sensitive=False),
    default="json",
    show_default=True,
)
@click.option("--reset-cache", is_flag=True, default=False, help="Reset cache between scenario runs")
def snapshot_scenarios(plan: str, format_: str, reset_cache: bool) -> None:
    """Run snapshot scenarios defined in a JSON plan file."""

    orchestrator = SnapshotOrchestrator()
    plan_path = Path(plan)
    if plan_path.suffix.lower() in {".toml", ".tml"}:
        with plan_path.open("rb") as handle:
            plan_payload = tomllib.load(handle)
    else:
        with plan_path.open(encoding="utf-8") as handle:
            plan_payload = json.load(handle)
    scenarios_value = plan_payload.get("scenarios")
    scenarios_raw = scenarios_value if isinstance(scenarios_value, list) else []
    defaults_value = plan_payload.get("defaults")
    defaults = defaults_value if isinstance(defaults_value, dict) else {}
    default_base = defaults.get("base_currency")
    default_commodities = defaults.get("commodity_symbols")
    default_jurisdictions = defaults.get("jurisdictions")

    scenarios = []
    for item in scenarios_raw:
        if not isinstance(item, dict):
            continue
        item_with_defaults = dict(item)
        if not item_with_defaults.get("base_currency") and default_base:
            item_with_defaults["base_currency"] = default_base
        if item_with_defaults.get("commodity_symbols") is None and default_commodities is not None:
            item_with_defaults["commodity_symbols"] = default_commodities
        if item_with_defaults.get("jurisdictions") is None and default_jurisdictions is not None:
            item_with_defaults["jurisdictions"] = default_jurisdictions
        scenarios.append(SnapshotScenario.from_mapping(item_with_defaults))

    batch = orchestrator.run_scenarios(scenarios, reset_cache_between_runs=reset_cache)
    payload = cast(dict[str, Any], scenario_batch_to_payload(batch))

    if format_.lower() == "json":
        click.echo(json.dumps(payload, default=str))
        return

    click.echo("Scenarios")
    results_value = payload.get("results")
    results: list[Any] = results_value if isinstance(results_value, list) else []
    for result in results:
        if not isinstance(result, dict):
            continue
        click.echo(f"- {result['name']}: providers={result.get('providers')}")
    click.echo("\nScenario Summary")
    click.echo(_json_dump(payload["summary"]))


@cli.command("inspect-plan")
@click.option("--plan", required=True, type=click.Path(exists=True))
@click.option(
    "--format",
    "format_",
    type=click.Choice(["json", "table"], case_sensitive=False),
    default="json",
)
def inspect_plan(plan: str, format_: str) -> None:
    """Inspect a scenario plan file and output a summary."""

    plan_path = Path(plan)
    if plan_path.suffix.lower() in {".toml", ".tml"}:
        with plan_path.open("rb") as handle:
            payload = tomllib.load(handle)
    else:
        with plan_path.open(encoding="utf-8") as handle:
            payload = json.load(handle)

    scenarios_payload = payload.get("scenarios")
    scenarios_raw = list(scenarios_payload) if isinstance(scenarios_payload, list) else []
    defaults = payload.get("defaults") or {}
    default_base = defaults.get("base_currency")
    scenarios = []
    for item in scenarios_raw:
        if not isinstance(item, dict):
            continue
        item_with_defaults = dict(item)
        if not item_with_defaults.get("base_currency") and default_base:
            item_with_defaults["base_currency"] = default_base
        scenarios.append(SnapshotScenario.from_mapping(item_with_defaults))
    summary = {
        "scenario_count": len(scenarios),
        "base_currencies": sorted({scenario.base_currency for scenario in scenarios}),
        "commodity_symbols": sorted({symbol for s in scenarios for symbol in s.commodity_symbols}),
    }
    output = {"plan": payload, "summary": summary}
    if format_.lower() == "json":
        click.echo(json.dumps(output, default=str))
    else:
        click.echo(_json_dump(output))


@cli.command("scaffold-extension")
@click.argument("key")
@click.option("--directory", default=".", type=click.Path())
@click.option("--capability", "capabilities", multiple=True, help="Capabilities to advertise")
def scaffold_extension_command(key: str, directory: str, capabilities: tuple[str, ...]) -> None:
    """Generate an extension package skeleton."""

    target_dir = Path(directory)
    scaffold_extension(target_dir, key=key, capabilities=capabilities)
    click.echo(f"Scaffolded extension '{key}' in {target_dir}")


@cli.command("import-csv")
@click.option("--file", "file_", required=True, type=click.Path(exists=True))
def import_csv(file_: str) -> None:
    """Import ledger postings from ``file`` containing CSV data."""

    with logging_context(command="import-csv", file=file_):
        with traced("cli.import_csv", file=file_):
            init_db()
            with Session(engine) as session:
                service = LedgerService(session)
                with open(file_, encoding="utf-8") as handle:
                    reader = csv.DictReader(handle)
                    for row in reader:
                        txn_date = date.fromisoformat(row["date"])
                        description = row["description"]
                        account_code = row["account_code"]
                        debit = float(row.get("debit", 0) or 0)
                        credit = float(row.get("credit", 0) or 0)
                        currency = row.get("currency", "USD")

                        account = session.exec(select(Account).where(Account.code == account_code)).first()
                        if not account:
                            click.echo(f"Account {account_code} not found, skipping row", err=True)
                            continue

                        postings = [
                            {
                                "account_id": account.id,
                                "debit": debit,
                                "credit": credit,
                                "currency": currency,
                            }
                        ]
                        service.post_transaction(txn_date, description, postings)
                click.echo(f"Imported CSV from {file_}")


if __name__ == "__main__":  # pragma: no cover - manual invocation guard
    cli()
