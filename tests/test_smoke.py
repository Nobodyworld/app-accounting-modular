from datetime import date

from sqlmodel import Session, SQLModel, create_engine, select

from apps.api.models.models import JournalEntry
from apps.api.services.ledger_service import LedgerService

# Test database
engine = create_engine("sqlite:///:memory:", echo=False)


def setup_module() -> None:
    SQLModel.metadata.create_all(engine)


def test_create_account() -> None:
    with Session(engine) as s:
        ls = LedgerService(s)
        acct = ls.create_account("Cash", "ASSET", "1000")
        assert acct.name == "Cash"
        assert acct.type == "ASSET"


def test_post_transaction() -> None:
    with Session(engine) as s:
        ls = LedgerService(s)
        acct = ls.create_account("Cash", "ASSET", "1000")
        txn = ls.post_transaction(
            date.today(),
            "Test",
            [{"account_id": acct.id, "debit": 100, "credit": 0, "currency": "USD"}],
        )
        assert txn.description == "Test"
        count = s.exec(select(JournalEntry).where(JournalEntry.transaction_id == txn.id)).all()
        assert len(count) == 1


def test_trial_balance() -> None:
    with Session(engine) as s:
        ls = LedgerService(s)
        acct = ls.create_account("Cash", "ASSET", "1000")
        ls.post_transaction(
            date.today(),
            "Test",
            [{"account_id": acct.id, "debit": 100, "credit": 0, "currency": "USD"}],
        )
        balance = ls.trial_balance()
        assert acct.id in balance
        assert balance[acct.id]["net"] == 100


def test_smoke() -> None:
    assert True
