from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlmodel import SQLModel, Session, create_engine
from apps.api.services.ledger_service import LedgerService, TrialBalanceRow


def create_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_trial_balance_totals_balance() -> None:
    with create_session() as session:
        ledger = LedgerService(session)
        cash = ledger.create_account(name="Cash", type="ASSET", code="1000")
        revenue = ledger.create_account(name="Revenue", type="REVENUE", code="4000")

        ledger.post_transaction(
            date=date(2024, 1, 1),
            description="Sale",
            postings=[
                {"account_id": cash.id, "debit": 150.0, "credit": 0.0},
                {"account_id": revenue.id, "debit": 0.0, "credit": 150.0},
            ],
        )

        trial_balance = ledger.trial_balance()
        rows = {row.account_code: row for row in trial_balance["rows"]}

        assert isinstance(rows["1000"], TrialBalanceRow)
        assert rows["1000"].debit == Decimal("150.0")
        assert rows["1000"].credit == Decimal("0")
        assert rows["1000"].balance == Decimal("150.0")

        assert rows["4000"].debit == Decimal("0")
        assert rows["4000"].credit == Decimal("150.0")
        assert rows["4000"].balance == Decimal("-150.0")

        assert trial_balance["total_debit"] == Decimal("150.0")
        assert trial_balance["total_credit"] == Decimal("150.0")


def test_trial_balance_includes_zero_activity_accounts() -> None:
    with create_session() as session:
        ledger = LedgerService(session)
        cash = ledger.create_account(name="Cash", type="ASSET", code="1000")
        revenue = ledger.create_account(name="Revenue", type="REVENUE", code="4000")
        ledger.create_account(name="Retained Earnings", type="EQUITY", code="3000")

        ledger.post_transaction(
            date=date(2024, 1, 2),
            description="Capital Injection",
            postings=[
                {"account_id": cash.id, "debit": 200.0, "credit": 0.0},
                {"account_id": revenue.id, "debit": 0.0, "credit": 200.0},
            ],
        )

        trial_balance = ledger.trial_balance()
        rows = {row.account_code: row for row in trial_balance["rows"]}
        assert "3000" in rows
        assert rows["3000"].debit == Decimal("0")
        assert rows["3000"].credit == Decimal("0")
