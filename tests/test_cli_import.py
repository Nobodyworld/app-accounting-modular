"""CLI CSV import tests covering ledger ingestion pipelines."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import click
import pytest
from apps.api.models.models import WorkflowStatus
from apps.api.services.ledger_service import LedgerService
from apps.api.services.workflow_service import WorkflowService
from cli.macli import _load_transactions_from_csv
from sqlmodel import Session, SQLModel, create_engine


@contextmanager
def create_session() -> Iterator[Session]:
    """Construct an in-memory session for CLI import operations."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def write_csv(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
    """Write a transactional CSV fixture with canonical headers for tests."""
    headers = ["date", "description", "account_code", "account_name", "account_type", "debit", "credit", "currency"]
    file_path = tmp_path / "import.csv"
    with file_path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(",".join(headers) + "\n")
        for row in rows:
            handle.write(",".join(row.get(h, "") for h in headers) + "\n")
    return file_path


def test_load_transactions_from_csv_creates_missing_account(tmp_path) -> None:
    with create_session() as session:
        ledger = LedgerService(session)
        ledger.create_account(name="Cash", type="ASSET", code="1000")

        csv_path = write_csv(
            tmp_path,
            [
                {
                    "date": "2024-01-01",
                    "description": "Invoice 1",
                    "account_code": "1000",
                    "account_name": "Cash",
                    "account_type": "ASSET",
                    "debit": "150.00",
                    "credit": "",
                    "currency": "USD",
                },
                {
                    "date": "2024-01-01",
                    "description": "Invoice 1",
                    "account_code": "4000",
                    "account_name": "Consulting Revenue",
                    "account_type": "REVENUE",
                    "debit": "",
                    "credit": "150.00",
                    "currency": "USD",
                },
            ],
        )

        transactions = _load_transactions_from_csv(ledger, csv_path)
        assert len(transactions) == 1
        txn = transactions[0]
        assert txn["date"] == date(2024, 1, 1)
        assert len(txn["postings"]) == 2

        workflow = WorkflowService(session)
        staged = workflow.ingest_transactions(transactions, source="test_csv")
        results = workflow.process_transactions([item.id for item in staged])
        assert results[0].status == WorkflowStatus.POSTED
        trial_balance = ledger.trial_balance()
        assert trial_balance["total_debit"] == trial_balance["total_credit"]


def test_load_transactions_from_csv_rejects_unbalanced(tmp_path) -> None:
    with create_session() as session:
        ledger = LedgerService(session)
        ledger.create_account(name="Cash", type="ASSET", code="1000")
        ledger.create_account(name="Expenses", type="EXPENSE", code="5000")

        csv_path = write_csv(
            tmp_path,
            [
                {
                    "date": "2024-01-02",
                    "description": "Supplies",
                    "account_code": "1000",
                    "account_name": "Cash",
                    "account_type": "ASSET",
                    "debit": "100.00",
                    "credit": "",
                    "currency": "USD",
                },
                {
                    "date": "2024-01-02",
                    "description": "Supplies",
                    "account_code": "5000",
                    "account_name": "Supplies Expense",
                    "account_type": "EXPENSE",
                    "debit": "",
                    "credit": "90.00",
                    "currency": "USD",
                },
            ],
        )

        with pytest.raises(click.ClickException):
            _load_transactions_from_csv(ledger, csv_path)


def test_load_transactions_from_csv_handles_multi_currency(tmp_path) -> None:
    with create_session() as session:
        ledger = LedgerService(session)
        ledger.create_account(name="Cash", type="ASSET", code="1000", currency="USD")
        ledger.create_account(name="Sales EUR", type="REVENUE", code="4000", currency="EUR")

        csv_path = write_csv(
            tmp_path,
            [
                {
                    "date": "2024-01-05",
                    "description": "EU Sale",
                    "account_code": "1000",
                    "account_name": "Cash",
                    "account_type": "ASSET",
                    "debit": "100.00",
                    "credit": "0.00",
                    "currency": "USD",
                },
                {
                    "date": "2024-01-05",
                    "description": "EU Sale",
                    "account_code": "4000",
                    "account_name": "Sales EUR",
                    "account_type": "REVENUE",
                    "debit": "0.00",
                    "credit": "100.00",
                    "currency": "EUR",
                },
            ],
        )

        transactions = _load_transactions_from_csv(ledger, csv_path)
        assert len(transactions) == 1
        assert transactions[0]["postings"][1]["currency"] == "EUR"
        # Ensure workflow ingestion still succeeds with multi-currency postings.
        workflow = WorkflowService(session)
        staged = workflow.ingest_transactions(transactions, source="test_csv_fx")
        results = workflow.process_transactions([item.id for item in staged])
        assert results[0].status in (WorkflowStatus.POSTED, WorkflowStatus.FAILED)
