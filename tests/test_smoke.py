from datetime import date

from apps.api.models.models import JournalEntry
from apps.api.services.ledger_service import LedgerService
from sqlmodel import Session, SQLModel, create_engine, select

# Test database
engine = create_engine("sqlite:///:memory:", echo=False)


def setup_module() -> None:
    SQLModel.metadata.create_all(engine)


def teardown_module() -> None:
    engine.dispose()


def test_create_account() -> None:
    with Session(engine) as s:
        ls = LedgerService(s)
        acct = ls.create_account("Cash", "ASSET", "1000")
        assert acct.name == "Cash"
        assert acct.type == "ASSET"


def test_post_transaction() -> None:
    with Session(engine) as s:
        ls = LedgerService(s)
        cash = ls.create_account("Posting Cash", "ASSET", "1001")
        revenue = ls.create_account("Posting Revenue", "REVENUE", "4001")
        txn = ls.post_transaction(
            date.today(),
            "Test",
            [
                {"account_id": cash.id, "debit": 100, "credit": 0, "currency": "USD"},
                {"account_id": revenue.id, "debit": 0, "credit": 100, "currency": "USD"},
            ],
        )
        assert txn.description == "Test"
        entries = s.exec(select(JournalEntry).where(JournalEntry.transaction_id == txn.id)).all()
        assert len(entries) == 2


def test_trial_balance() -> None:
    with Session(engine) as s:
        ls = LedgerService(s)
        cash = ls.create_account("Balance Cash", "ASSET", "1002")
        equity = ls.create_account("Balance Equity", "EQUITY", "3002")
        ls.post_transaction(
            date.today(),
            "Test",
            [
                {"account_id": cash.id, "debit": 100, "credit": 0, "currency": "USD"},
                {"account_id": equity.id, "debit": 0, "credit": 100, "currency": "USD"},
            ],
        )
        balance = ls.trial_balance()
        assert cash.id in balance
        assert balance[cash.id]["net"] == 100
        assert balance["total_debit"] == balance["total_credit"] == 100


def test_smoke() -> None:
    assert True