from __future__ import annotations

from datetime import date
from pathlib import Path

import click
import pytest
from sqlmodel import SQLModel, Session, create_engine

from apps.api.services.ledger_service import LedgerService
from cli.macli import _load_transactions_from_csv


def create_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def write_csv(tmp_path: Path, rows: list[dict[str, str]]) -> Path:
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

        # Persist the postings and ensure balances are correct
        ledger.post_transaction(txn["date"], txn["description"], txn["postings"])
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
