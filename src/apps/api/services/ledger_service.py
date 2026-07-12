from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from sqlmodel import Session, select

from ..audit import AuditAction, AuditLogger, apply_creation_metadata
from ..models.models import Account, AccountType, JournalEntry, Rate, Transaction


@dataclass(slots=True)
class TrialBalanceRow:
    """Denormalised trial balance line item."""

    account_id: int
    account_code: str | None
    account_name: str
    account_type: AccountType
    currency: str
    debit: Decimal
    credit: Decimal
    balance: Decimal


class LedgerService:
    def __init__(
        self,
        session: Session,
        organization_id: int | None = None,
        *,
        audit_logger: AuditLogger | None = None,
    ):
        self.s = session
        self.organization_id = organization_id
        self.audit = audit_logger or AuditLogger(session)

    # ------------------------------------------------------------------
    # Account management
    # ------------------------------------------------------------------
    def _coerce_account_type(self, value: AccountType | str) -> AccountType:
        if isinstance(value, AccountType):
            return value
        try:
            return AccountType(value.upper())
        except Exception as exc:
            raise ValueError(f"Unsupported account type '{value}'") from exc

    def create_account(
        self,
        name: str,
        type: AccountType | str,
        code: str | None = None,
        currency: str = "USD",
        organization_id: int | None = None,
    ) -> Account:
        org_id = organization_id or self.organization_id
        if not name or not name.strip():
            raise ValueError("Account name cannot be blank")
        account_type = self._coerce_account_type(type)

        if code and org_id is not None:
            stmt = select(Account).where(Account.code == code, Account.organization_id == org_id)
            existing = self.s.exec(stmt).first()
            if existing:
                raise ValueError("Account code already exists")

        account = Account(
            name=name.strip(),
            type=account_type,
            code=code,
            currency=currency,
            organization_id=org_id,
        )
        apply_creation_metadata(account)
        self.s.add(account)
        self.s.commit()
        self.s.refresh(account)
        return account

    def require_account(self, identifier: int | str) -> Account:
        stmt = select(Account)
        if isinstance(identifier, int):
            stmt = stmt.where(Account.id == identifier)
        else:
            identifier = identifier.strip()
            if not identifier:
                raise ValueError("account reference cannot be blank")
            stmt = stmt.where((Account.code == identifier) | (Account.name == identifier))
        if self.organization_id is not None:
            stmt = stmt.where(Account.organization_id == self.organization_id)
        account = self.s.exec(stmt).first()
        if account is None:
            raise ValueError(f"account {identifier} not found")
        return account

    # ------------------------------------------------------------------
    # Transaction posting
    # ------------------------------------------------------------------
    @staticmethod
    def _coerce_amount(value: object, *, posting_index: int, field: str) -> Decimal:
        try:
            return Decimal(str(value or 0))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError(f"Posting {posting_index}: {field} must be numeric") from exc

    def validate_transaction(
        self, date: date, description: str, postings: Iterable[dict[str, Any]]
    ) -> list[dict[str, object]]:
        del date  # Reserved for future period-close validation.
        if not description or not description.strip():
            raise ValueError("Transaction description is required")
        posting_list = list(postings)
        if len(posting_list) < 2:
            raise ValueError("At least two postings are required")

        normalised: list[dict[str, object]] = []
        total_debit = Decimal("0")
        total_credit = Decimal("0")
        currencies: set[str] = set()

        for idx, posting in enumerate(posting_list, start=1):
            account_ref = posting.get("account_id")
            if account_ref is None:
                raise ValueError(f"Posting {idx}: account reference is required")
            if not isinstance(account_ref, (int, str)):
                raise ValueError(f"Posting {idx}: account reference must be int or str")
            account = self.require_account(account_ref)

            debit = self._coerce_amount(posting.get("debit", 0), posting_index=idx, field="debit")
            credit = self._coerce_amount(posting.get("credit", 0), posting_index=idx, field="credit")
            if debit < 0 or credit < 0:
                raise ValueError("Debit and credit amounts must be non-negative")
            if debit > 0 and credit > 0:
                raise ValueError(f"Posting {idx}: specify either debit or credit, not both")
            if debit == 0 and credit == 0:
                raise ValueError(f"Posting {idx}: either debit or credit must be provided")

            currency = str(posting.get("currency") or account.currency).strip().upper()
            if not currency:
                raise ValueError(f"Posting {idx}: currency is required")
            currencies.add(currency)
            normalised.append(
                {
                    "account_id": account.id,
                    "debit": debit,
                    "credit": credit,
                    "currency": currency,
                }
            )
            total_debit += debit
            total_credit += credit

        if len(currencies) > 1:
            raise ValueError("Mixed-currency transactions require an explicit conversion policy")
        if total_debit != total_credit:
            raise ValueError("Transaction is not balanced")

        return normalised

    def post_transaction(
        self,
        date: date,
        description: str,
        postings: Iterable[dict[str, object]],
        *,
        source: str | None = None,
        source_reference: str | None = None,
    ) -> Transaction:
        normalised = self.validate_transaction(date, description, postings)

        txn = Transaction(
            date=date,
            description=description.strip(),
            organization_id=self.organization_id,
            external_ref=source_reference,
        )
        apply_creation_metadata(txn)
        self.s.add(txn)
        self.s.flush()
        txn_id = txn.id
        if txn_id is None:
            raise ValueError("transaction missing identifier after flush")
        for posting in normalised:
            account_id_value = cast(Any, posting["account_id"])
            debit_value = cast(Any, posting["debit"])
            credit_value = cast(Any, posting["credit"])
            currency_value = cast(Any, posting["currency"])
            je = JournalEntry(
                transaction_id=txn_id,
                account_id=int(account_id_value),
                debit=float(debit_value),
                credit=float(credit_value),
                currency=str(currency_value),
            )
            self.s.add(je)
        self.s.commit()
        self.s.refresh(txn)

        self.audit.log(
            AuditAction.CREATE,
            "Transaction",
            txn.id,
            after={
                "date": txn.date.isoformat(),
                "description": txn.description,
                "source": source,
                "source_reference": source_reference,
                "postings": [
                    {
                        "account_id": posting["account_id"],
                        "debit": float(cast(Any, posting["debit"])),
                        "credit": float(cast(Any, posting["credit"])),
                        "currency": posting["currency"],
                    }
                    for posting in normalised
                ],
                "organization_id": txn.organization_id,
            },
        )
        return txn

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------
    def trial_balance(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        currency: str | None = None,
    ) -> dict[str, object]:
        accounts_stmt = select(Account)
        if self.organization_id is not None:
            accounts_stmt = accounts_stmt.where(Account.organization_id == self.organization_id)
        accounts = list(self.s.exec(accounts_stmt))
        totals: dict[int, dict[str, Decimal]] = {}
        for account in accounts:
            if account.id is None:
                continue
            totals[account.id] = {"debit": Decimal("0"), "credit": Decimal("0")}

        if accounts:
            stmt = (
                select(JournalEntry, Transaction, Account)
                .join(Transaction, cast(Any, Transaction.id) == cast(Any, JournalEntry.transaction_id))
                .join(Account, cast(Any, Account.id) == cast(Any, JournalEntry.account_id))
            )
            if self.organization_id is not None:
                stmt = stmt.where(Account.organization_id == self.organization_id)
            if start_date is not None:
                stmt = stmt.where(Transaction.date >= start_date)
            if end_date is not None:
                stmt = stmt.where(Transaction.date <= end_date)
            for entry, txn, account in self.s.exec(stmt):
                account_id = int(entry.account_id)
                debit_amount = entry.debit
                credit_amount = entry.credit
                txn_date = txn.date
                acct_currency = account.currency
                debit_dec = Decimal(str(debit_amount or 0))
                credit_dec = Decimal(str(credit_amount or 0))
                if currency and acct_currency and acct_currency != currency:
                    rate = (
                        self.s.exec(
                            select(cast(Any, Rate.value))
                            .where(Rate.base == acct_currency)
                            .where(Rate.quote == currency)
                            .where(Rate.date <= txn_date)
                            .order_by(cast(Any, Rate.date).desc())
                        ).first()
                        or None
                    )
                    if rate is None:
                        raise ValueError(
                            f"Missing FX rate for {acct_currency}/{currency} on or before {txn_date.isoformat()}"
                        )
                    factor = Decimal(str(rate))
                    debit_dec *= factor
                    credit_dec *= factor
                totals[int(account_id)]["debit"] += debit_dec
                totals[int(account_id)]["credit"] += credit_dec

        rows: list[TrialBalanceRow] = []
        account_map: dict[object, object] = {}
        for account in accounts:
            if account.id is None:
                continue
            account_totals = totals.get(account.id, {"debit": Decimal("0"), "credit": Decimal("0")})
            debit_decimal = account_totals["debit"]
            credit_decimal = account_totals["credit"]
            balance_decimal = debit_decimal - credit_decimal
            rows.append(
                TrialBalanceRow(
                    account_id=int(account.id),
                    account_code=account.code,
                    account_name=account.name,
                    account_type=account.type,
                    currency=currency or account.currency,
                    debit=debit_decimal,
                    credit=credit_decimal,
                    balance=balance_decimal,
                )
            )
            account_map[int(account.id)] = {
                "debit": debit_decimal,
                "credit": credit_decimal,
                "net": balance_decimal,
            }

        total_debit = sum((row.debit for row in rows), start=Decimal("0"))
        total_credit = sum((row.credit for row in rows), start=Decimal("0"))
        account_map["rows"] = rows
        account_map["total_debit"] = total_debit
        account_map["total_credit"] = total_credit
        return cast(dict[str, object], account_map)


__all__ = ["LedgerService", "TrialBalanceRow"]