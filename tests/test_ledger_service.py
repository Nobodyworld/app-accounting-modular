"""Ledger service unit tests covering trial balance reporting behaviours."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

import pytest
from apps.api.models.models import JournalEntry, Organization, Rate, Transaction
from apps.api.services.ledger_service import LedgerService, TrialBalanceRow
from sqlmodel import Session, SQLModel, create_engine, select


@contextmanager
def create_session() -> Iterator[Session]:
    """Construct an isolated SQLModel session for ledger-related tests."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_trial_balance_totals_balance() -> None:
    with create_session() as session:
        org = Organization(name="Test Org")
        session.add(org)
        session.commit()
        session.refresh(org)

        ledger = LedgerService(session, organization_id=org.id)
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


def test_post_transaction_captures_source_metadata() -> None:
    with create_session() as session:
        org = Organization(name="Test Org")
        session.add(org)
        session.commit()
        session.refresh(org)

        ledger = LedgerService(session, organization_id=org.id)
        cash = ledger.create_account(name="Cash", type="ASSET", code="1000")
        revenue = ledger.create_account(name="Revenue", type="REVENUE", code="4000")

        txn = ledger.post_transaction(
            date=date(2024, 2, 1),
            description="Sale",
            postings=[
                {"account_id": cash.id, "debit": 50.0, "credit": 0.0},
                {"account_id": revenue.id, "debit": 0.0, "credit": 50.0},
            ],
            source="api",
            source_reference="upload-123",
        )
        assert txn.external_ref == "upload-123"


def test_trial_balance_includes_zero_activity_accounts() -> None:
    with create_session() as session:
        org = Organization(name="Test Org")
        session.add(org)
        session.commit()
        session.refresh(org)

        ledger = LedgerService(session, organization_id=org.id)
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


def test_trial_balance_filters_and_converts_currency() -> None:
    with create_session() as session:
        org = Organization(name="Test Org")
        session.add(org)
        session.commit()
        session.refresh(org)

        ledger = LedgerService(session, organization_id=org.id)
        usd = ledger.create_account(name="Cash", type="ASSET", code="USD", currency="USD")
        eur = ledger.create_account(name="Sales", type="REVENUE", code="EUR", currency="EUR")

        session.add_all(
            [
                Transaction(date=date(2024, 1, 1), description="usd", organization_id=org.id),
                Transaction(date=date(2024, 1, 2), description="eur", organization_id=org.id),
                Rate(base="EUR", quote="USD", date=date(2024, 1, 2), value=2.0, provider="stub"),
            ]
        )
        session.commit()
        txns = session.exec(select(Transaction).order_by(Transaction.date)).all()
        session.add_all(
            [
                JournalEntry(transaction_id=txns[0].id, account_id=usd.id, debit=100, credit=0, currency="USD"),
                JournalEntry(transaction_id=txns[0].id, account_id=usd.id, debit=0, credit=100, currency="USD"),
                JournalEntry(transaction_id=txns[1].id, account_id=eur.id, debit=0, credit=50, currency="EUR"),
            ]
        )
        session.commit()

        tb = ledger.trial_balance(start_date=date(2024, 1, 2), currency="USD")
        rows = {row.account_code: row for row in tb["rows"]}
        assert "USD" in rows
        assert "EUR" in rows
        assert rows["USD"].balance == Decimal("0")
        assert rows["EUR"].balance == Decimal("-100")


def test_create_account_rejects_blank_name() -> None:
    with create_session() as session:
        org = Organization(name="Test Org")
        session.add(org)
        session.commit()
        session.refresh(org)

        ledger = LedgerService(session, organization_id=org.id)
        with pytest.raises(ValueError):
            ledger.create_account(name="   ", type="ASSET")


def test_create_account_rejects_duplicate_code() -> None:
    with create_session() as session:
        org = Organization(name="Test Org")
        session.add(org)
        session.commit()
        session.refresh(org)

        ledger = LedgerService(session, organization_id=org.id)
        ledger.create_account(name="Cash", type="ASSET", code="1000")
        with pytest.raises(ValueError):
            ledger.create_account(name="Bank", type="ASSET", code="1000")


def test_post_transaction_requires_balanced_entries() -> None:
    with create_session() as session:
        org = Organization(name="Test Org")
        session.add(org)
        session.commit()
        session.refresh(org)

        ledger = LedgerService(session, organization_id=org.id)
        cash = ledger.create_account(name="Cash", type="ASSET", code="1000")
        expense = ledger.create_account(name="Expenses", type="EXPENSE", code="5000")

        with pytest.raises(ValueError):
            ledger.post_transaction(
                date=date(2024, 2, 1),
                description="Unbalanced",
                postings=[
                    {"account_id": cash.id, "debit": 100.0, "credit": 0.0},
                    {"account_id": expense.id, "debit": 0.0, "credit": 90.0},
                ],
            )


def test_post_transaction_requires_existing_account() -> None:
    with create_session() as session:
        org = Organization(name="Test Org")
        session.add(org)
        session.commit()
        session.refresh(org)

        ledger = LedgerService(session, organization_id=org.id)
        cash = ledger.create_account(name="Cash", type="ASSET", code="1000")

        with pytest.raises(ValueError):
            ledger.post_transaction(
                date=date(2024, 2, 2),
                description="Missing account",
                postings=[
                    {"account_id": 9999, "debit": 100.0, "credit": 0.0},
                    {"account_id": cash.id, "debit": 0.0, "credit": 100.0},
                ],
            )


# TODO - (ledger) Extend coverage to reversing entries and multi-org postings.
def test_post_transaction_supports_reversing_entries() -> None:
    with create_session() as session:
        org = Organization(name="Test Org")
        session.add(org)
        session.commit()
        session.refresh(org)

        ledger = LedgerService(session, organization_id=org.id)
        cash = ledger.create_account(name="Cash", type="ASSET", code="1000")
        revenue = ledger.create_account(name="Revenue", type="REVENUE", code="4000")

        txn = ledger.post_transaction(
            date=date(2024, 3, 1),
            description="Sale",
            postings=[
                {"account_id": cash.id, "debit": 300.0, "credit": 0.0},
                {"account_id": revenue.id, "debit": 0.0, "credit": 300.0},
            ],
        )

        reversing = ledger.post_transaction(
            date=date(2024, 3, 15),
            description="Reverse Sale",
            postings=[
                {"account_id": cash.id, "debit": 0.0, "credit": 300.0},
                {"account_id": revenue.id, "debit": 300.0, "credit": 0.0},
            ],
            source="reversal",
            source_reference=str(txn.id),
        )
        assert reversing.external_ref == str(txn.id)
        tb = ledger.trial_balance()
        rows = {row.account_code: row for row in tb["rows"]}
        assert rows["1000"].balance == Decimal("0")
        assert rows["4000"].balance == Decimal("0")


def test_multi_org_postings_isolated() -> None:
    with create_session() as session:
        org1 = Organization(name="Org1")
        org2 = Organization(name="Org2")
        session.add_all([org1, org2])
        session.commit()
        session.refresh(org1)
        session.refresh(org2)

        ledger1 = LedgerService(session, organization_id=org1.id)
        ledger2 = LedgerService(session, organization_id=org2.id)
        cash1 = ledger1.create_account(name="Cash1", type="ASSET", code="C1")
        cash2 = ledger2.create_account(name="Cash2", type="ASSET", code="C2")

        ledger1.post_transaction(
            date=date(2024, 4, 1),
            description="Org1 txn",
            postings=[{"account_id": cash1.id, "debit": 10.0, "credit": 0.0}],
        )
        ledger2.post_transaction(
            date=date(2024, 4, 2),
            description="Org2 txn",
            postings=[{"account_id": cash2.id, "debit": 20.0, "credit": 0.0}],
        )

        tb1 = ledger1.trial_balance()
        tb2 = ledger2.trial_balance()
        codes1 = {row.account_code for row in tb1["rows"]}
        codes2 = {row.account_code for row in tb2["rows"]}
        assert "C1" in codes1 and "C1" not in codes2
        assert "C2" in codes2 and "C2" not in codes1
