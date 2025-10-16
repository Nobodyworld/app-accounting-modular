from sqlmodel import Session, select
from ..models.models import Account, Transaction, JournalEntry
from typing import Iterable

class LedgerService:
    def __init__(self, session: Session):
        self.s = session

    def create_account(self, name: str, type: str, code: str | None = None, currency: str = "USD") -> Account:
        acct = Account(name=name, type=type, code=code, currency=currency)
        self.s.add(acct)
        self.s.commit()
        self.s.refresh(acct)
        return acct

    def post_transaction(self, date, description, postings: Iterable[dict]) -> Transaction:
        txn = Transaction(date=date, description=description)
        self.s.add(txn)
        self.s.flush()
        for p in postings:
            je = JournalEntry(transaction_id=txn.id, **p)
            self.s.add(je)
        self.s.commit()
        self.s.refresh(txn)
        return txn

    def trial_balance(self):
        # Simple trial balance: sum debits/credits per account
        rows = self.s.exec(select(JournalEntry.account_id)).all()
        # TODO: implement aggregated SQL with group by (kept concise for brevity)
        # # TODO implement full report queries (P&L, Balance Sheet)
        return {"# TODO": "Implement trial balance aggregate"}
