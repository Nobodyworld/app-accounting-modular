from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type
from decimal import Decimal, InvalidOperation
from typing import Iterable, Mapping, Sequence

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
    """High-level orchestration of ledger operations."""

    def __init__(self, session: Session):
        self.s = session

    def create_account(
        self, name: str, type: AccountType | str, code: str | None = None, currency: str = "USD"
    ) -> Account:
        """Create and persist an account."""

        acct_type = AccountType(type) if isinstance(type, str) else type

        code_clean = code.strip() if isinstance(code, str) and code.strip() else None
        currency_clean = currency.strip().upper() if isinstance(currency, str) else "USD"

        if code_clean and self.find_account_by_code(code_clean):
            raise ValueError(f"Account code '{code_clean}' already exists")

        acct = Account(name=name_clean, type=acct_type, code=code_clean, currency=currency_clean)
        self.s.add(acct)
        self.s.commit()
        self.s.refresh(acct)
        return acct

    def find_account_by_code(self, code: str) -> Account | None:
        """Return the account with the provided code, if any."""

        stmt = select(Account).where(Account.code == code)
        return self.s.exec(stmt).one_or_none()

    def find_account_by_name(self, name: str) -> Account | None:
        """Return the account with the provided name, if any."""

        stmt = select(Account).where(Account.name == name)
        return self.s.exec(stmt).one_or_none()

    def require_account(self, identifier: str) -> Account:
        """Return the account matching ``identifier`` or raise ``ValueError``."""

        account = self.find_account_by_code(identifier) or self.find_account_by_name(identifier)
        if account is None:
            raise ValueError(f"Account '{identifier}' not found")
        return account

    def post_transaction(
        self, date, description: str, postings: Iterable[dict[str, object]]
    ) -> Transaction:
        """Persist a transaction and its postings."""

        txn = Transaction(date=date, description=description)
        self.s.add(txn)
        self.s.flush()
        for posting in postings:
            je = JournalEntry(transaction_id=txn.id, **posting)
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
