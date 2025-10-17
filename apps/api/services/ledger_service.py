from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable, Sequence

from sqlalchemy import func
from sqlmodel import Session, select

from ..models.models import Account, AccountType, JournalEntry, Transaction


@dataclass(slots=True, frozen=True)
class TrialBalanceRow:
    """Summary of postings per account."""

    account_id: int
    account_code: str | None
    account_name: str
    account_type: AccountType
    currency: str
    debit: Decimal
    credit: Decimal

    @property
    def balance(self) -> Decimal:
        return self.debit - self.credit

class LedgerService:
    def __init__(self, session: Session):
        self.s = session

    def create_account(
        self, name: str, type: AccountType | str, code: str | None = None, currency: str = "USD"
    ) -> Account:
        acct_type = AccountType(type) if isinstance(type, str) else type
        acct = Account(name=name, type=acct_type, code=code, currency=currency)
        self.s.add(acct)
        self.s.commit()
        self.s.refresh(acct)
        return acct

    def find_account_by_code(self, code: str) -> Account | None:
        stmt = select(Account).where(Account.code == code)
        return self.s.exec(stmt).one_or_none()

    def find_account_by_name(self, name: str) -> Account | None:
        stmt = select(Account).where(Account.name == name)
        return self.s.exec(stmt).one_or_none()

    def require_account(self, identifier: str) -> Account:
        account = self.find_account_by_code(identifier) or self.find_account_by_name(identifier)
        if account is None:
            raise ValueError(f"Account '{identifier}' not found")
        return account

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

    def trial_balance(self) -> dict[str, Sequence[TrialBalanceRow] | Decimal]:
        """Return summed debits and credits per account."""

        currency_expr = func.coalesce(JournalEntry.currency, Account.currency).label("currency")
        stmt = (
            select(
                Account.id,
                Account.code,
                Account.name,
                Account.type,
                currency_expr,
                func.coalesce(func.sum(JournalEntry.debit), 0.0),
                func.coalesce(func.sum(JournalEntry.credit), 0.0),
            )
            .join(JournalEntry, JournalEntry.account_id == Account.id, isouter=True)
            .group_by(
                Account.id,
                Account.code,
                Account.name,
                Account.type,
                currency_expr,
            )
            .order_by(Account.code, Account.name, currency_expr)
        )

        rows: list[TrialBalanceRow] = []
        total_debit = Decimal("0")
        total_credit = Decimal("0")

        for acct_id, code, name, type_, currency, debit, credit in self.s.exec(stmt):
            acct_type = AccountType(type_) if not isinstance(type_, AccountType) else type_
            debit_dec = _to_decimal(debit)
            credit_dec = _to_decimal(credit)
            rows.append(
                TrialBalanceRow(
                    account_id=acct_id,
                    account_code=code,
                    account_name=name,
                    account_type=acct_type,
                    currency=currency,
                    debit=debit_dec,
                    credit=credit_dec,
                )
            )
            total_debit += debit_dec
            total_credit += credit_dec

        return {
            "rows": rows,
            "total_debit": total_debit,
            "total_credit": total_credit,
        }


def _to_decimal(value: float | int | Decimal | None) -> Decimal:
    try:
        if isinstance(value, Decimal):
            return value
        if value is None:
            return Decimal("0")
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"Invalid monetary value: {value!r}") from exc
