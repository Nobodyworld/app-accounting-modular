from sqlmodel import Session, select, func
from ..models.models import Account, Transaction, JournalEntry, AccountType
from typing import Iterable
from datetime import date

class LedgerService:
    def __init__(self, session: Session):
        self.s = session

    def create_account(self, name: str, type: AccountType, code: str | None = None, currency: str = "USD") -> Account:
        acct = Account(name=name, type=type, code=code, currency=currency)
        self.s.add(acct)
        self.s.commit()
        self.s.refresh(acct)
        return acct

    def post_transaction(self, date: date, description: str, postings: Iterable[dict]) -> Transaction:
        txn = Transaction(date=date, description=description)
        self.s.add(txn)
        self.s.flush()
        for p in postings:
            je = JournalEntry(transaction_id=txn.id, **p)  # type: ignore
            self.s.add(je)
        self.s.commit()
        self.s.refresh(txn)
        return txn

    def trial_balance(self) -> dict:
        # Aggregate debits and credits per account
        query = select(
            JournalEntry.account_id,
            func.sum(JournalEntry.debit).label("total_debit"),
            func.sum(JournalEntry.credit).label("total_credit")
        ).group_by(JournalEntry.account_id)
        results = self.s.exec(query).all()
        
        balance = {}
        for account_id, debit, credit in results:
            net = (debit or 0) - (credit or 0)
            balance[account_id] = {"debit": debit or 0, "credit": credit or 0, "net": net}
        
        return balance
