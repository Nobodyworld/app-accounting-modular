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

    def __init__(self, session: Session, organization_id: int):
        self.s = session
        self.organization_id = organization_id

    def create_account(
        self,
        name: str,
        type: AccountType | str,
        code: str | None = None,
        currency: str = "USD",
        organization_id: int | None = None,
    ) -> Account:
        """Create and persist an account."""

        name_clean = (name or "").strip()
        if not name_clean:
            raise ValueError("Account name is required")

        if isinstance(type, str):
            try:
                acct_type = AccountType(type.strip().upper())
            except ValueError as exc:
                raise ValueError(f"Unknown account type '{type}'") from exc
        else:
            acct_type = type

        code_clean = code.strip() if isinstance(code, str) and code.strip() else None
        currency_clean = (currency or "USD").strip().upper() or "USD"

        if code_clean and self.find_account_by_code(code_clean):
            raise ValueError(f"Account code '{code_clean}' already exists")

        acct = Account(
            name=name_clean,
            type=acct_type,
            code=code_clean,
            currency=currency_clean,
          # todo - fix
            organization_id=organization_id,
            organization_id=self.organization_id,
        )
        self.s.add(acct)
        self.s.commit()
        self.s.refresh(acct)
        return acct

    def find_account_by_code(self, code: str) -> Account | None:
        """Return the account with the provided code, if any."""

        stmt = select(Account).where(
            Account.code == code, Account.organization_id == self.organization_id
        )
        return self.s.exec(stmt).one_or_none()

    def find_account_by_name(self, name: str) -> Account | None:
        """Return the account with the provided name, if any."""

        stmt = select(Account).where(
            Account.name == name, Account.organization_id == self.organization_id
        )
        return self.s.exec(stmt).one_or_none()

    def require_account(self, identifier: str) -> Account:
        """Return the account matching ``identifier`` or raise ``ValueError``."""

        account = self.find_account_by_code(identifier) or self.find_account_by_name(identifier)
        if account is None:
            raise ValueError(f"Account '{identifier}' not found")
        return account

    def validate_transaction(
        self, date: date_type, description: str, postings: Iterable[Mapping[str, object]]
    ) -> list[dict[str, object]]:
        """Validate transaction inputs and return normalised postings."""

        description_clean = (description or "").strip()
        if not description_clean:
            raise ValueError("Transaction description is required")

        postings_list = [dict(p) for p in postings]
        if not postings_list:
            raise ValueError("At least one posting is required")

        debit_total = Decimal("0")
        credit_total = Decimal("0")
        normalised_postings: list[dict[str, object]] = []

        for idx, posting in enumerate(postings_list, start=1):
            account_id = posting.get("account_id")
            if not isinstance(account_id, int):
                raise ValueError(f"Posting {idx}: account_id is required")

            account = self.s.get(Account, account_id)
            if account is None or account.organization_id != self.organization_id:
                raise ValueError(f"Posting {idx}: account {account_id} not found")

            debit_val = _to_decimal(posting.get("debit"))
            credit_val = _to_decimal(posting.get("credit"))

            if debit_val < 0 or credit_val < 0:
                raise ValueError(f"Posting {idx}: debit and credit must be non-negative")
            if (debit_val == 0) == (credit_val == 0):
                raise ValueError(
                    f"Posting {idx}: exactly one of debit or credit must be provided"
                )

            currency_val = posting.get("currency")
            currency_clean = (
                (currency_val or account.currency).strip().upper()
                if isinstance(currency_val, str)
                else account.currency
            )

            debit_total += debit_val
            credit_total += credit_val

            normalised_postings.append(
                {
                    "account_id": account_id,
                    "debit": float(debit_val),
                    "credit": float(credit_val),
                    "currency": currency_clean,
                }
            )

        if debit_total != credit_total:
            raise ValueError("Transaction is not balanced")

        txn = Transaction(
            date=date,
            description=description_clean,
            organization_id=self.organization_id,
        )
        self.s.add(txn)
        self.s.flush()

        for entry in normalised_postings:
            self.s.add(
                JournalEntry(
                    transaction_id=txn.id,
                    organization_id=self.organization_id,
                    **entry,
                )
            )

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
            .join(
                JournalEntry,
                (JournalEntry.account_id == Account.id)
                & (JournalEntry.organization_id == self.organization_id),
                isouter=True,
            )
            .where(Account.organization_id == self.organization_id)
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


def _to_decimal(value: float | int | Decimal | str | None) -> Decimal:
    try:
        if isinstance(value, Decimal):
            return value
        if value is None:
            return Decimal("0")
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return Decimal("0")
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"Invalid monetary value: {value!r}") from exc
