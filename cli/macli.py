"""Command line tooling for Modular Accounting."""

from __future__ import annotations

import asyncio
import csv
import json
import logging
from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast
from uuid import uuid4

import click
from sqlmodel import Session, select

from apps.api.audit import AuditActor, apply_creation_metadata, use_actor
from apps.api.config import LogFormat, get_settings
from apps.api.db import engine, init_db
from apps.api.models.models import AccountType, Organization, User, WorkflowStatus
from apps.api.services.extension_loader import (
    active_extensions,
    load_configured_extensions,
)
from apps.api.services.fx_service import FXService
from apps.api.services.health import register_default_health_checks
from apps.api.services.ledger_service import LedgerService
from apps.api.services.market_service import MarketService
from apps.api.services.plugin_loader import (
    ProviderHandle,
    available_providers,
    load_provider,
)
from apps.api.services.snapshot_service import (
    SnapshotOrchestrator,
    scenario_batch_to_payload,
)
from apps.api.services.workflow_service import WorkflowService
from apps.extensions import extension_registry
from apps.extensions import scaffold_extension as generate_extension
from apps.modular_accounting.application import (
    ScenarioPlan,
    ScenarioPlanFormatError,
    ScenarioPlanSummary,
    ScenarioPlanValidationError,
    load_plan_from_bytes,
)
from apps.observability.diagnostics import collect_observability_snapshot
from apps.observability.health import health_registry
from apps.observability.logging import configure_logging, logging_context
from apps.observability.tracing import configure_tracing, traced
from cli.snapshot_render import (
    format_scenario_batch_table,
    format_snapshot_table,
)

logger = logging.getLogger(__name__)


def _resolve_provider_key(capability: str, provider_key: str | None) -> str:
    """Return a valid provider key, falling back to the configured default."""

    catalog = available_providers(capability)
    keys = [meta.key for meta in catalog]
    if provider_key:
        if provider_key not in keys:
            message = (
                f"Unknown {capability} provider '{provider_key}'. "
                f"Configured providers: {', '.join(sorted(keys)) or 'none'}"
            )
            raise click.BadParameter(message, param_hint=f"--{capability}-provider")
        return provider_key

    if not catalog:
        raise click.BadParameter(
            f"No providers configured for capability '{capability}'",
            param_hint=f"--{capability}-provider",
        )
    return keys[0]


def _execute_provider_command(
    command: str,
    capability: str,
    provider_key: str | None,
    scope_context: dict[str, object],
    runner: Callable[[Session, ProviderHandle], int],
) -> tuple[ProviderHandle, int]:
    """Execute a provider-backed CLI operation within a logged scope."""

    # agent-safe-task: provider orchestration for automated sync routines.

    resolved_key = _resolve_provider_key(capability, provider_key)
    with _command_scope(command, provider_key=resolved_key, **scope_context):
        init_db()
        handle = load_provider(resolved_key)
        with Session(engine) as session:
            actor = _ensure_cli_actor(session)
            with use_actor(actor):
                processed = runner(session, handle)
        return handle, processed


@contextmanager
def _command_scope(command: str, **context: object) -> Iterator[None]:
    correlation = f"{command}-{uuid4()}"
    merged_context = {"command": command, **context}
    with traced(f"cli.{command}", **merged_context):
        with logging_context(
            correlation_id=correlation,
            request_id=correlation,
            **merged_context,
        ):
            logger.info("Starting CLI command")
            try:
                yield
            except Exception:
                logger.exception("CLI command failed")
                raise
            else:
                logger.info("Completed CLI command")


def _load_scenario_plan(path: Path) -> ScenarioPlan:
    """Load a scenario plan from disk and return the parsed object."""

    try:
        content = path.read_bytes()
    except OSError as exc:  # pragma: no cover - filesystem errors are rare
        raise click.BadParameter(
            f"Failed to read scenario plan: {exc}", param_hint="--plan"
        ) from exc

    try:
        return load_plan_from_bytes(content, format_hint=path.suffix.lower())
    except ScenarioPlanFormatError as exc:
        raise click.BadParameter(str(exc), param_hint="--plan") from exc
    except ScenarioPlanValidationError as exc:
        raise click.BadParameter(str(exc), param_hint="--plan") from exc


@click.group()
@click.option(
    "--log-format",
    type=click.Choice(["json", "text"], case_sensitive=False),
    default=None,
    help="Override log output format for this invocation.",
)
@click.pass_context
def cli(ctx: click.Context, log_format: str | None) -> None:
    """Modular Accounting CLI."""

    settings = get_settings()
    selected_format = (log_format or settings.log_format).upper()
    configure_logging(
        settings.log_level,
        cast(LogFormat, selected_format),
        service_name="modular-accounting-cli",
        force=True,
    )
    configure_tracing(
        service_name="modular-accounting-cli",
        exporter=settings.tracing_exporter,
        endpoint=settings.tracing_otlp_endpoint,
    )
    ctx.ensure_object(dict)
    ctx.obj["log_format"] = selected_format
    logger.info(
        "CLI initialised",
        extra={"log_format": selected_format, "log_level": settings.log_level},
    )


def _format_extension_rows() -> list[dict[str, str]]:
    load_configured_extensions()
    rows: list[dict[str, str]] = []
    for status in active_extensions():
        manifest = status.manifest
        rows.append(
            {
                "Key": status.key,
                "Name": manifest.name if manifest else "-",
                "Module": status.module,
                "Enabled": "yes" if status.enabled else "no",
                "Loaded": "yes" if manifest else "no",
                "Version": manifest.version if manifest else "-",
                "Capabilities": ", ".join(manifest.capabilities) if manifest else "-",
            }
        )
    return rows


def _render_table(rows: list[dict[str, str]]) -> str:
    headers = [
        "Key",
        "Name",
        "Module",
        "Enabled",
        "Loaded",
        "Version",
        "Capabilities",
    ]
    if not rows:
        return "No extensions configured."
    widths = {header: len(header) for header in headers}
    for row in rows:
        for header in headers:
            widths[header] = max(widths[header], len(row[header]))
    lines = [
        "  ".join(header.ljust(widths[header]) for header in headers),
        "  ".join("-" * widths[header] for header in headers),
    ]
    for row in rows:
        lines.append("  ".join(row[header].ljust(widths[header]) for header in headers))
    return "\n".join(lines)


@cli.command(name="inspect-extensions")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    show_default=True,
    help="Output format for the extension registry snapshot.",
)
def inspect_extensions(output_format: str) -> None:
    """Display configured extension manifests and load status."""

    rows = _format_extension_rows()
    if output_format.lower() == "json":
        click.echo(json.dumps(rows, indent=2, sort_keys=True))
        return
    click.echo(_render_table(rows))


def _format_contract_rows() -> list[dict[str, str]]:
    load_configured_extensions()
    rows: list[dict[str, str]] = []
    for status in active_extensions():
        contracts = extension_registry.contracts_for(status.key)
        for contract in contracts:
            rows.append(
                {
                    "Extension": status.key,
                    "Kind": contract.kind,
                    "Name": contract.name,
                    "Version": contract.version,
                    "Entrypoint": contract.entrypoint or "-",
                    "Tags": ", ".join(contract.tags) if contract.tags else "-",
                }
            )
    rows.sort(key=lambda row: (row["Extension"], row["Kind"], row["Name"]))
    return rows


def _render_contract_table(rows: list[dict[str, str]]) -> str:
    headers = ["Extension", "Kind", "Name", "Version", "Entrypoint", "Tags"]
    if not rows:
        return "No contracts registered."
    widths = {header: len(header) for header in headers}
    for row in rows:
        for header in headers:
            widths[header] = max(widths[header], len(row[header]))
    lines = [
        "  ".join(header.ljust(widths[header]) for header in headers),
        "  ".join("-" * widths[header] for header in headers),
    ]
    for row in rows:
        lines.append("  ".join(row[header].ljust(widths[header]) for header in headers))
    return "\n".join(lines)


@cli.command(name="inspect-contracts")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    show_default=True,
    help="Output format for the contract registry snapshot.",
)
def inspect_contracts(output_format: str) -> None:
    """Display registered extension contracts for automation planning."""

    rows = _format_contract_rows()
    if output_format.lower() == "json":
        snapshot: list[dict[str, object]] = []
        for status in active_extensions():
            manifest = status.manifest
            contracts = [
                contract.serialise()
                for contract in extension_registry.contracts_for(status.key)
            ]
            snapshot.append(
                {
                    "key": status.key,
                    "module": status.module,
                    "enabled": status.enabled,
                    "loaded": manifest is not None,
                    "version": manifest.version if manifest else None,
                    "contracts": contracts,
                }
            )
        click.echo(json.dumps(snapshot, indent=2, sort_keys=True))
        return
    click.echo(_render_contract_table(rows))


def _render_observability_table(snapshot) -> str:
    summary = snapshot.as_dict()
    lines = [
        f"Snapshot generated at {summary['generated_at']}",
        "",
        "Metrics:",
        f"  lines: {summary['metrics']['lines']}",
        f"  bytes: {summary['metrics']['bytes']}",
        "  checks: " + ", ".join(summary['metrics']['checks'])
        if summary['metrics']['checks']
        else "  checks: <none>",
        "",
        "Health by severity:",
    ]
    if summary["health"]["by_severity"]:
        for severity, stats in summary["health"]["by_severity"].items():
            lines.append(
                f"  {severity}: {stats['open']} open / {stats['total']} total"
            )
    else:
        lines.append("  <no checks registered>")

    if summary["incidents"]:
        lines.append("")
        lines.append("Open incidents:")
        for incident in summary["incidents"]:
            lines.append(
                "  - {name} ({severity}): {action}".format(**incident)
            )
    else:
        lines.append("")
        lines.append("Open incidents: none")

    tracing = summary["tracing"]
    lines.extend(
        [
            "",
            "Tracing:",
            f"  enabled: {'yes' if tracing['enabled'] else 'no'}",
            f"  exporter: {tracing['exporter']}",
            f"  otel_enabled: {'yes' if tracing['otel_enabled'] else 'no'}",
        ]
    )
    if "endpoint" in tracing:
        lines.append(f"  endpoint: {tracing['endpoint']}")

    lines.append("")
    lines.append("Extensions:")
    if summary["extensions"]:
        for extension in summary["extensions"]:
            state = "enabled" if extension["enabled"] else "disabled"
            loaded = "loaded" if extension["loaded"] else "not loaded"
            capabilities = ", ".join(extension["capabilities"]) or "<none>"
            lines.append(
                f"  - {extension['key']} ({state}, {loaded}) -> {capabilities}"
            )
    else:
        lines.append("  <no extensions configured>")

    return "\n".join(lines)


@cli.command(name="observe")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    show_default=True,
    help="Output format for the observability snapshot.",
)
def observe(output_format: str) -> None:
    """Summarise metrics, health, and tracing state for operators."""

    load_configured_extensions()
    snapshot = asyncio.run(
        collect_observability_snapshot(
            extension_status_provider=active_extensions
        )
    )
    if output_format.lower() == "json":
        click.echo(json.dumps(snapshot.as_dict(), indent=2, sort_keys=True))
        return
    click.echo(_render_observability_table(snapshot))


@cli.command()
@click.option(
    "--base",
    default="USD",
    show_default=True,
    help="Base currency to synchronise",
)
@click.option(
    "--provider",
    "provider_key",
    default=None,
    help="Configured FX provider key (defaults to first configured provider).",
)
def sync_fx(base: str, provider_key: str | None) -> None:
    """Synchronise foreign-exchange rates using the configured provider."""

    handle, count = _execute_provider_command(
        "sync-fx",
        "fx",
        provider_key,
        {"base_currency": base},
        lambda session, handle: FXService(session, handle.instance).sync(base=base),
    )
    logger.info(
        "FX rates synchronised",
        extra={
            "provider": handle.metadata.key,
            "base_currency": base,
            "rates_synced": count,
        },
    )
    click.echo(
        f"Synced {count} FX rates via {handle.metadata.name} "
        f"({handle.metadata.key})"
    )


@cli.command()
@click.argument("symbol")
@click.option("--start", required=True, help="ISO date for the start of the range")
@click.option("--end", required=True, help="ISO date for the end of the range")
@click.option(
    "--provider",
    "provider_key",
    default=None,
    help="Configured market data provider key (defaults to first configured provider).",
)
def sync_prices(
    symbol: str,
    start: str,
    end: str,
    provider_key: str | None,
) -> None:
    """Synchronise historical prices for ``symbol``."""

    try:
        start_date = date.fromisoformat(start)
    except ValueError as exc:  # pragma: no cover - defensive formatting branch
        raise click.BadParameter("--start must be a valid ISO date") from exc
    try:
        end_date = date.fromisoformat(end)
    except ValueError as exc:  # pragma: no cover - defensive formatting branch
        raise click.BadParameter("--end must be a valid ISO date") from exc

    handle, count = _execute_provider_command(
        "sync-prices",
        "market",
        provider_key,
        {"symbol": symbol, "start": start, "end": end},
        lambda session, handle: MarketService(session, handle.instance).sync_prices(
            symbol, start_date, end_date
        ),
    )
    logger.info(
        "Market prices synchronised",
        extra={
            "provider": handle.metadata.key,
            "symbol": symbol,
            "start": start,
            "end": end,
            "prices_synced": count,
        },
    )
    click.echo(
        f"Synced {count} prices for {symbol} "
        f"via {handle.metadata.name} ({handle.metadata.key})"
    )


@cli.command()
# agent-entrypoint: expose snapshot orchestration for automation and agents.
@click.option(
    "--base",
    "base_currency",
    default="USD",
    show_default=True,
    help="Base currency used for FX rates.",
)
@click.option(
    "--commodity",
    "commodity_symbols",
    multiple=True,
    help="Commodity symbols to include; pass multiple times to add more.",
)
@click.option(
    "--jurisdiction",
    "jurisdictions",
    multiple=True,
    help="Jurisdictions used to filter tax rules.",
)
@click.option(
    "--fx-provider",
    "fx_provider_key",
    default=None,
    help="Override the configured FX provider key (defaults to service configuration).",
)
@click.option(
    "--commodity-provider",
    "commodity_provider_key",
    default=None,
    help=(
        "Override the configured commodity provider key "
        "(defaults to service configuration)."
    ),
)
@click.option(
    "--tax-provider",
    "tax_provider_key",
    default=None,
    help="Override the configured tax provider key (defaults to service configuration).",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "table"], case_sensitive=False),
    default="json",
    show_default=True,
    help="Choose JSON or table output.",
)
def snapshot(
    base_currency: str,
    commodity_symbols: tuple[str, ...],
    jurisdictions: tuple[str, ...],
    fx_provider_key: str | None,
    commodity_provider_key: str | None,
    tax_provider_key: str | None,
    output_format: str,
) -> None:
    """Build a consolidated snapshot across FX, commodity, and tax providers."""

    with _command_scope(
        "snapshot",
        base_currency=base_currency,
        commodities=list(commodity_symbols),
        jurisdictions=list(jurisdictions),
    ):
        orchestrator = SnapshotOrchestrator(
            fx_provider_key=fx_provider_key,
            commodity_provider_key=commodity_provider_key,
            tax_provider_key=tax_provider_key,
        )
        result = orchestrator.build_snapshot(
            base_currency=base_currency,
            commodity_symbols=commodity_symbols or None,
            jurisdictions=jurisdictions or None,
        )
        payload = result.as_payload()
        if output_format.lower() == "json":
            click.echo(json.dumps(payload, indent=2, default=str))
            return

        provider_line = ", ".join(
            f"{cap}={key}" for cap, key in sorted(result.providers.items())
        )
        click.echo(f"Providers: {provider_line}")
        click.echo("")
        click.echo(format_snapshot_table(result.snapshot, result.diagnostics))
        if result.cache_stats:
            stats_line = ", ".join(
                f"{name}: hits={stats.hits}, misses={stats.misses}, size={stats.size}"
                for name, stats in result.cache_stats.items()
            )
            click.echo("")
            click.echo(f"Cache stats: {stats_line}")


@cli.command(name="snapshot-scenarios")
@click.option(
    "--plan",
    "plan_path",
    required=True,
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    help="Path to a JSON or TOML file describing snapshot scenarios.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "table"], case_sensitive=False),
    default="json",
    show_default=True,
    help="Choose JSON or table output for the batch report.",
)
@click.option(
    "--reset-cache/--no-reset-cache",
    "reset_cache",
    default=False,
    show_default=True,
    help="Clear the service cache between scenarios for deterministic diagnostics.",
)
def snapshot_scenarios(
    plan_path: Path, output_format: str, reset_cache: bool
) -> None:
    """Execute multiple snapshot scenarios from a plan file."""

    plan = _load_scenario_plan(plan_path)
    scenarios = plan.scenarios
    with _command_scope(
        "snapshot-scenarios",
        plan=str(plan_path),
        plan_name=plan.metadata.name,
        scenario_count=len(scenarios),
        reset_cache=reset_cache,
    ):
        orchestrator = SnapshotOrchestrator()
        batch = orchestrator.run_scenarios(
            scenarios, reset_cache_between_runs=reset_cache
        )
        if output_format.lower() == "json":
            payload = scenario_batch_to_payload(batch)
            payload["plan"] = plan.as_payload(include_scenarios=False)
            click.echo(json.dumps(payload, indent=2, default=str))
            return

        click.echo(format_scenario_batch_table(batch))


def _format_plan_summary_table(plan: ScenarioPlan, summary: ScenarioPlanSummary) -> str:
    lines = [
        f"Plan: {plan.metadata.name}",
        f"Description: {plan.metadata.description or '—'}",
        f"Schedule: {plan.metadata.schedule or '—'}",
        "",
        "Scenarios",
        "---------",
        f"Total: {summary.scenario_count}",
        f"Names: {', '.join(s.name for s in plan.scenarios)}",
        f"Base currencies: {', '.join(summary.base_currencies) or '—'}",
        f"Commodities: {', '.join(summary.commodity_symbols) or '—'}",
        f"Jurisdictions: {', '.join(summary.jurisdictions) or '—'}",
        f"Defaults applied: {', '.join(summary.defaults_applied) or '—'}",
        "",
        "Tags",
        "----",
    ]

    if summary.tag_counts:
        tag_lines = [f"{tag}: {count}" for tag, count in sorted(summary.tag_counts.items())]
        lines.extend(tag_lines)
    else:
        lines.append("(none)")

    if plan.metadata.parameters:
        lines.extend(["", "Parameters", "----------"])
        for key, value in sorted(plan.metadata.parameters.items()):
            lines.append(f"{key}: {value}")

    return "\n".join(lines)


@cli.command(name="inspect-plan")
@click.option(
    "--plan",
    "plan_path",
    required=True,
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    help="Path to a JSON or TOML scenario plan file.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "table"], case_sensitive=False),
    default="table",
    show_default=True,
    help="Render the plan summary as a table or JSON payload.",
)
def inspect_plan(plan_path: Path, output_format: str) -> None:
    """Display a plan summary without executing any providers."""

    plan = _load_scenario_plan(plan_path)
    summary = plan.summary()
    with _command_scope(
        "inspect-plan",
        plan=str(plan_path),
        plan_name=plan.metadata.name,
        scenario_count=summary.scenario_count,
    ):
        if output_format.lower() == "json":
            payload = {
                "plan": plan.as_payload(),
                "summary": summary.as_payload(),
            }
            click.echo(json.dumps(payload, indent=2, default=str))
            return

        click.echo(_format_plan_summary_table(plan, summary))


@cli.command()
@click.option(
    "--file",
    "file_",
    required=True,
    type=click.Path(exists=True, path_type=Path),
)
def import_csv(file_: Path) -> None:
    """Import journal postings from a CSV file."""

    with _command_scope("import-csv", file=str(file_)):
        init_db()
        with Session(engine) as session:
            actor = _ensure_cli_actor(session)
            with use_actor(actor):
                ledger = LedgerService(session)
                transactions = _load_transactions_from_csv(ledger, file_)
                workflow = WorkflowService(session)
                staged = workflow.ingest_transactions(
                    transactions,
                    source="cli_csv",
                    source_reference=str(file_.resolve()),
                    metadata={"filename": file_.name},
                )
                results = workflow.process_transactions([txn.id for txn in staged])

        posted = sum(
            1 for result in results if result.status == WorkflowStatus.POSTED
        )
        failed = [
            result for result in results if result.status == WorkflowStatus.FAILED
        ]

        if failed:
            logger.warning(
                "Validation failures encountered during CSV import",
                extra={
                    "failed_count": len(failed),
                    "file": file_.name,
                },
            )
        logger.info(
            "CSV import processed",
            extra={
                "file": file_.name,
                "transactions": len(results),
                "posted": posted,
                "failed": len(failed),
            },
        )

        for result in failed:
            message = "; ".join(result.validation_errors or []) or "Unknown error"
            click.echo(
                (
                    f"Transaction {result.staged_transaction_id} "
                    f"failed validation: {message}"
                ),
                err=True,
            )

        click.echo(
            f"Processed {len(results)} transactions from {file_.name} "
            f"({posted} posted, {len(failed)} failed)"
        )


@cli.command()
def health() -> None:
    """Execute registered health checks and display their status."""

    with _command_scope("health"):
        register_default_health_checks()
        load_configured_extensions()
        reports = asyncio.run(health_registry.evaluate())
        overall = all(report.healthy for report in reports)
        for report in reports:
            state = "PASS" if report.healthy else "FAIL"
            details = ", ".join(
                f"{key}={value}" for key, value in report.details.items()
            )
            click.echo(
                (
                    f"[{state}] {report.name} "
                    f"(severity={report.severity}) {details}"
                ).strip()
            )
        click.echo("Overall status: OK" if overall else "Overall status: DEGRADED")


@cli.command(name="extensions")
def list_extensions() -> None:
    """List configured extensions and their activation state."""

    with _command_scope("extensions"):
        load_configured_extensions()
        statuses = active_extensions()
        if not statuses:
            click.echo("No extensions configured")
            return
        for status in statuses:
            state = "enabled" if status.enabled else "disabled"
            manifest = status.manifest
            description = manifest.description if manifest else "<not loaded>"
            click.echo(f"{status.key}: {state} - {description}")


@cli.command(name="scaffold-extension")
@click.argument("key")
@click.option(
    "--directory",
    type=click.Path(path_type=Path),
    default=Path("plugins"),
    help="Directory to create the extension package in.",
)
@click.option("--name", default=None, help="Human readable extension name.")
@click.option(
    "--capability",
    "capabilities",
    multiple=True,
    help="Capability label to advertise (repeat for multiple).",
)
@click.option(
    "--version",
    default="0.1.0",
    show_default=True,
    help="Initial manifest version.",
)
@click.option("--description", default=None, help="Short extension summary.")
@click.option("--author", default=None, help="Manifest author metadata.")
@click.option("--force", is_flag=True, help="Overwrite existing files if present.")
@click.option(
    "--observability-contract/--no-observability-contract",
    default=False,
    help="Generate a starter observability playbook contract.",
)
def scaffold_extension_command(
    key: str,
    directory: Path,
    name: str | None,
    capabilities: tuple[str, ...],
    version: str,
    description: str | None,
    author: str | None,
    force: bool,
    observability_contract: bool,
) -> None:
    """Generate an extension package skeleton."""

    target_dir = directory.resolve()
    with _command_scope(
        "scaffold-extension", key=key, directory=str(target_dir)
    ):
        try:
            result = generate_extension(
                target_dir,
                key=key,
                name=name,
                version=version,
                description=description,
                capabilities=capabilities,
                author=author,
                force=force,
                observability_contract=observability_contract,
            )
        except (ValueError, FileExistsError) as exc:
            raise click.ClickException(str(exc)) from exc

        for created in result.created_files:
            click.echo(f"created {created.relative_to(Path.cwd())}")
        click.echo(
            f"Extension package '{result.key}' scaffolded at {result.root.relative_to(Path.cwd())}"
        )


def _load_transactions_from_csv(
    ledger: LedgerService, file_path: Path
) -> list[dict[str, object]]:
    """Parse a CSV file into ledger transaction payloads."""

    required_fields = {"date", "description", "debit", "credit"}
    optional_account_fields = ("account_code", "account_name")

    with file_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        account_key = _validate_csv_structure(
            reader, required_fields, optional_account_fields
        )
        grouped = _collect_postings(reader, ledger, account_key)

    return _assemble_transactions(grouped)


def _validate_csv_structure(
    reader: csv.DictReader,
    required_fields: set[str],
    optional_account_fields: tuple[str, ...],
) -> str:
    """Validate header constraints and return the selected account identifier column."""

    if reader.fieldnames is None:
        raise click.ClickException("CSV file is missing a header row")

    header = {name.strip() for name in reader.fieldnames if name}
    missing = required_fields - header
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise click.ClickException(f"CSV missing required columns: {missing_list}")

    account_key = next((field for field in optional_account_fields if field in header), None)
    if account_key is None:
        raise click.ClickException(
            "CSV must include either 'account_code' or 'account_name' column"
        )
    return account_key


def _collect_postings(
    reader: csv.DictReader,
    ledger: LedgerService,
    account_key: str,
) -> dict[tuple[str, str], list[dict[str, object]]]:
    """Return postings grouped by transaction identity."""

    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    account_cache: dict[str, int] = {}

    for idx, row in enumerate(reader, start=2):  # 1-index header
        if not any(row.values()):
            continue

        txn_date = _parse_row_date(row, idx)
        description = _require_field(row, "description", idx)
        identifier = _require_field(row, account_key, idx)

        account_id = _resolve_account(ledger, account_cache, identifier, row)
        debit, credit = _parse_posting_amounts(row, idx)
        currency = _normalise_optional_str(row.get("currency"))

        grouped[(txn_date.isoformat(), description)].append(
            {
                "account_id": account_id,
                "debit": float(debit),
                "credit": float(credit),
                "currency": currency,
            }
        )

    return grouped


def _parse_row_date(row: dict[str, str | None], idx: int) -> date:
    try:
        raw_date = (row.get("date") or "").strip()
        return date.fromisoformat(raw_date)
    except (ValueError, AttributeError) as exc:  # pragma: no cover - defensive
        raise click.ClickException(f"Row {idx}: invalid or missing date") from exc


def _require_field(row: dict[str, str | None], key: str, idx: int) -> str:
    value = (row.get(key) or "").strip()
    if not value:
        raise click.ClickException(f"Row {idx}: {key} is required")
    return value


def _parse_posting_amounts(
    row: dict[str, str | None], idx: int
) -> tuple[Decimal, Decimal]:
    debit = _to_decimal(row.get("debit"), idx, "debit")
    credit = _to_decimal(row.get("credit"), idx, "credit")

    if debit < 0 or credit < 0:
        raise click.ClickException(f"Row {idx}: debit and credit must be non-negative")
    if debit == 0 and credit == 0:
        raise click.ClickException(
            f"Row {idx}: either debit or credit must be provided"
        )
    if debit != 0 and credit != 0:
        raise click.ClickException(
            f"Row {idx}: provide only one of debit or credit for a posting"
        )
    return debit, credit


def _normalise_optional_str(value: str | None) -> str | None:
    result = (value or "").strip()
    return result or None


def _assemble_transactions(
    grouped: dict[tuple[str, str], list[dict[str, object]]]
) -> list[dict[str, object]]:
    """Collapse posting groups into balanced transaction payloads."""

    transactions: list[dict[str, object]] = []
    for (date_key, description), postings in grouped.items():
        debit_total = sum(Decimal(str(p["debit"])) for p in postings)
        credit_total = sum(Decimal(str(p["credit"])) for p in postings)
        if abs(debit_total - credit_total) > Decimal("0.005"):
            raise click.ClickException(
                f"Transaction '{description}' on {date_key} is not balanced"
            )

        transactions.append(
            {
                "date": date.fromisoformat(date_key),
                "description": description,
                "postings": postings,
            }
        )
    return transactions


def _ensure_cli_actor(session: Session) -> AuditActor:
    """Ensure a synthetic CLI actor exists and return its context."""

    org = session.exec(
        select(Organization).where(Organization.name == "CLI Runner")
    ).one_or_none()
    if org is None:
        org = Organization(name="CLI Runner")
        apply_creation_metadata(org)
        session.add(org)
        session.commit()
        session.refresh(org)

    user = session.exec(
        select(User).where(User.email == "cli@system.local")
    ).one_or_none()
    if user is None:
        user = User(email="cli@system.local", name="CLI User", organization_id=org.id)
        apply_creation_metadata(user)
        session.add(user)
        session.commit()
        session.refresh(user)

    return AuditActor(
        request_id=str(uuid4()),
        user_id=user.id,
        organization_id=org.id,
        source="cli",
        user_label=user.email or user.name,
    )


def _resolve_account(
    ledger: LedgerService,
    cache: dict[str, int],
    identifier: str,
    row: dict[str, str | None],
) -> int:
    """Look up an account by code/name, creating it on demand."""

    if identifier in cache:
        return cache[identifier]

    try:
        account = ledger.require_account(identifier)
    except ValueError:
        account_type_raw = (row.get("account_type") or "").strip().upper()
        try:
            account_type = AccountType(account_type_raw)
        except ValueError as exc:
            raise click.ClickException(
                f"Account '{identifier}' not found and no valid account_type provided"
            ) from exc
        currency = (row.get("currency") or "").strip() or "USD"
        name = (row.get("account_name") or identifier).strip() or identifier
        account = ledger.create_account(
            name=name,
            type=account_type,
            code=row.get("account_code"),
            currency=currency,
        )

    if account.id is None:
        raise click.ClickException(f"Account '{identifier}' could not be persisted")

    cache[identifier] = account.id
    return account.id


def _to_decimal(value: str | None, row_number: int, field: str) -> Decimal:
    """Convert a textual numeric value to :class:`Decimal`."""

    text = (value or "0").strip()
    if not text:
        text = "0"
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise click.ClickException(
            f"Row {row_number}: invalid {field} '{value}'"
        ) from exc
    return amount


if __name__ == "__main__":
    cli()
