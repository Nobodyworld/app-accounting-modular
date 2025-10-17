"""Command line interface for Modular Accounting."""

from __future__ import annotations

import csv

from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

import click
from sqlmodel import Session

from apps.api.db import engine, init_db
from apps.api.models.models import AccountType
from apps.api.services.fx_service import FXService
from apps.api.models.models import WorkflowStatus
from apps.api.services.ledger_service import LedgerService
from apps.api.services.workflow_service import WorkflowService
from apps.api.services.market_service import MarketService
from apps.api.services.plugin_loader import available_providers, load_provider


def _provider_keys(capability: str) -> tuple[list[str], str | None]:
    metas = available_providers(capability)
    keys = [meta.key for meta in metas]
    default = keys[0] if keys else None
    return keys, default


_FX_PROVIDER_KEYS, _DEFAULT_FX_PROVIDER = _provider_keys("fx")
_MARKET_PROVIDER_KEYS, _DEFAULT_MARKET_PROVIDER = _provider_keys("market")


@click.group()
def cli() -> None:
    """Modular Accounting CLI"""


@cli.command()
@click.option("--base", default="USD", show_default=True, help="Base currency to synchronise")
@click.option(
    "--provider",
    "provider_key",
    type=click.Choice(_FX_PROVIDER_KEYS) if _FX_PROVIDER_KEYS else str,
    default=_DEFAULT_FX_PROVIDER,
    show_default=_DEFAULT_FX_PROVIDER is not None,
    help="Configured FX provider key",
)
def sync_fx(base: str, provider_key: str) -> None:
    """Synchronise foreign-exchange rates using the configured provider."""

    init_db()
    handle = load_provider(provider_key)
    with Session(engine) as session:
        svc = FXService(session, handle.instance)
        count = svc.sync(base=base)
        click.echo(
            f"Synced {count} FX rates via {handle.metadata.name} ({handle.metadata.key})"
        )


@cli.command()
@click.argument("symbol")
@click.option("--start", required=True, help="ISO date for the start of the range")
@click.option("--end", required=True, help="ISO date for the end of the range")
@click.option(
    "--provider",
    "provider_key",
    type=click.Choice(_MARKET_PROVIDER_KEYS) if _MARKET_PROVIDER_KEYS else str,
    default=_DEFAULT_MARKET_PROVIDER,
    show_default=_DEFAULT_MARKET_PROVIDER is not None,
    help="Configured market data provider key",
)
def sync_prices(symbol: str, start: str, end: str, provider_key: str) -> None:
    """Synchronise historical prices for ``symbol``."""

    init_db()
    handle = load_provider(provider_key)
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    with Session(engine) as session:
        svc = MarketService(session, handle.instance)
        count = svc.sync_prices(symbol, start_date, end_date)
        click.echo(
            f"Synced {count} prices for {symbol} via {handle.metadata.name} ({handle.metadata.key})"
        )


@cli.command()
@click.option("--file", "file_", required=True, type=click.Path(exists=True, path_type=Path))
def import_csv(file_: Path) -> None:
    """Import journal postings from a CSV file."""

    init_db()
    with Session(engine) as session:
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

    posted = sum(1 for result in results if result.status == WorkflowStatus.POSTED)
    failed = [result for result in results if result.status == WorkflowStatus.FAILED]

    for result in failed:
        message = "; ".join(result.validation_errors or []) or "Unknown error"
        click.echo(
            f"Transaction {result.staged_transaction_id} failed validation: {message}",
            err=True,
        )

    click.echo(
        f"Processed {len(results)} transactions from {file_.name} "
        f"({posted} posted, {len(failed)} failed)"
    )


def _load_transactions_from_csv(
    ledger: LedgerService, file_path: Path
) -> list[dict[str, object]]:
    """Parse a CSV file into ledger transaction payloads."""

    required_fields = {"date", "description", "debit", "credit"}
    optional_account_fields = ("account_code", "account_name")

    with file_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise click.ClickException("CSV file is missing a header row")

        header = {name.strip() for name in reader.fieldnames if name}
        missing = required_fields - header
        if missing:
            raise click.ClickException(f"CSV missing required columns: {', '.join(sorted(missing))}")

        account_key = next((f for f in optional_account_fields if f in header), None)
        if account_key is None:
            raise click.ClickException(
                "CSV must include either 'account_code' or 'account_name' column"
            )

        grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
        account_cache: dict[str, int] = {}

        for idx, row in enumerate(reader, start=2):  # 1-index header
            if not any(row.values()):
                continue

            try:
                raw_date = (row.get("date") or "").strip()
                txn_date = date.fromisoformat(raw_date)
            except (ValueError, AttributeError) as exc:
                raise click.ClickException(f"Row {idx}: invalid or missing date") from exc

            description = (row.get("description") or "").strip()
            if not description:
                raise click.ClickException(f"Row {idx}: description is required")

            identifier = (row.get(account_key) or "").strip()
            if not identifier:
                raise click.ClickException(f"Row {idx}: {account_key} is required")

            account_id = _resolve_account(ledger, account_cache, identifier, row)

            debit = _to_decimal(row.get("debit"), idx, "debit")
            credit = _to_decimal(row.get("credit"), idx, "credit")

            if debit < 0 or credit < 0:
                raise click.ClickException(f"Row {idx}: debit and credit must be non-negative")
            if debit == 0 and credit == 0:
                raise click.ClickException(f"Row {idx}: either debit or credit must be provided")
            if debit != 0 and credit != 0:
                raise click.ClickException(
                    f"Row {idx}: provide only one of debit or credit for a posting"
                )

            currency = (row.get("currency") or "").strip() or None

            grouped[(txn_date.isoformat(), description)].append(
                {
                    "account_id": account_id,
                    "debit": float(debit),
                    "credit": float(credit),
                    "currency": currency,
                }
            )

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


def _resolve_account(
    ls: LedgerService, cache: dict[str, int], identifier: str, row: dict[str, str | None]
) -> int:
    """Look up an account by code/name, creating it on demand."""

    if identifier in cache:
        return cache[identifier]

    try:
        account = ls.require_account(identifier)
    except ValueError:
        account_type_raw = (row.get("account_type") or "").strip().upper()
        try:
            acct_type = AccountType(account_type_raw)
        except ValueError as exc:
            raise click.ClickException(
                f"Account '{identifier}' not found and no valid account_type provided"
            ) from exc
        currency = (row.get("currency") or "").strip() or "USD"
        name = (row.get("account_name") or identifier).strip() or identifier
        account = ls.create_account(
            name=name,
            type=acct_type,
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
        dec = Decimal(text)
    except InvalidOperation as exc:
        raise click.ClickException(f"Row {row_number}: invalid {field} '{value}'") from exc
    return dec


if __name__ == "__main__":
    cli()
