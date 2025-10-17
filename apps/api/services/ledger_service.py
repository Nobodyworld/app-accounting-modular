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
    def __init__(self, session: Session):
        self.s = session

    def create_account(
        self, name: str, type: AccountType | str, code: str | None = None, currency: str = "USD"
    ) -> Account:
        """Create and persist an account with basic validation."""

        name_clean = name.strip()
        if not name_clean:
            raise ValueError("Account name is required")

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
        code_clean = code.strip()
        stmt = select(Account).where(Account.code == code_clean)
        return self.s.exec(stmt).one_or_none()

    def find_account_by_name(self, name: str) -> Account | None:
        name_clean = name.strip()
        stmt = select(Account).where(Account.name == name_clean)
        return self.s.exec(stmt).one_or_none()

    def require_account(self, identifier: str | int) -> Account:
        account: Account | None
        if isinstance(identifier, int):
            account = self.s.get(Account, identifier)
        else:
            identifier_str = str(identifier).strip()
            account = self.find_account_by_code(identifier_str) or self.find_account_by_name(identifier_str)
            if account is None and identifier_str.isdigit():
                account = self.s.get(Account, int(identifier_str))
        if account is None:
            raise ValueError(f"Account '{identifier}' not found")
        return account

    def post_transaction(
        self,
        date: date_type,
        description: str,
        postings: Iterable[Mapping[str, object]],
        external_ref: str | None = None,
    ) -> Transaction:
        """Persist a balanced transaction composed of validated postings."""

        description_clean = description.strip()
        if not description_clean:
            raise ValueError("Transaction description is required")

        entries: list[JournalEntry] = []
        total_debit = Decimal("0")
        total_credit = Decimal("0")

        for idx, posting in enumerate(postings, start=1):
            try:
                account_id = int(posting["account_id"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Posting {idx}: account_id is required") from exc

            account = self.s.get(Account, account_id)
            if account is None:
                raise ValueError(f"Posting {idx}: account {account_id} not found")

            debit = _to_decimal(posting.get("debit"))
            credit = _to_decimal(posting.get("credit"))

            if debit < 0 or credit < 0:
                raise ValueError(f"Posting {idx}: debit and credit must be non-negative")
            if debit == 0 and credit == 0:
                raise ValueError(f"Posting {idx}: either debit or credit must be provided")
            if debit != 0 and credit != 0:
                raise ValueError(f"Posting {idx}: only one of debit or credit can be provided")

            currency_raw = posting.get("currency")
            currency = (str(currency_raw).strip().upper() if currency_raw else account.currency)

            entries.append(
                JournalEntry(
                    account_id=account_id,
                    debit=float(debit),
                    credit=float(credit),
                    currency=currency,
                )
            )

            total_debit += debit
            total_credit += credit

        if len(entries) < 2:
            raise ValueError("Transaction must contain at least two postings")

        if abs(total_debit - total_credit) > Decimal("0.005"):
            raise ValueError("Transaction is not balanced")

        txn = Transaction(date=date, description=description_clean, external_ref=external_ref)
        self.s.add(txn)
        self.s.flush()

        for entry in entries:
            entry.transaction_id = txn.id
            self.s.add(entry)

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
