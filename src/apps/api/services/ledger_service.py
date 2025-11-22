from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlmodel import Session, func, select

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
    def validate_transaction(
        self, date: date, description: str, postings: Iterable[dict[str, Any]]
    ) -> list[dict[str, object]]:
        if not description or not description.strip():
            raise ValueError("Transaction description is required")
        posting_list = list(postings)
        if not posting_list:
            raise ValueError("At least one posting is required")

        normalised: list[dict[str, object]] = []
        total_debit = Decimal("0")
        total_credit = Decimal("0")

        for idx, posting in enumerate(posting_list, start=1):
            account_ref = posting.get("account_id")
            if account_ref is None:
                raise ValueError(f"Posting {idx}: account reference is required")
            if not isinstance(account_ref, (int, str)):
                raise ValueError(f"Posting {idx}: account reference must be int or str")
            account = self.require_account(int(account_ref))

            debit = Decimal(str(posting.get("debit", 0) or 0))
            credit = Decimal(str(posting.get("credit", 0) or 0))
            if debit < 0 or credit < 0:
                raise ValueError("Debit and credit amounts must be non-negative")

            currency = posting.get("currency") or account.currency
            normalised.append(
                {
                    "account_id": account.id,
                    "debit": debit,
                    "credit": credit,
                    "currency": str(currency),
                }
            )
            total_debit += debit
            total_credit += credit

        if len(posting_list) > 1 and total_debit != total_credit:
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
        for posting in normalised:
            je = JournalEntry(
                transaction_id=txn.id,
                account_id=int(posting["account_id"]),
                debit=float(posting["debit"]),
                credit=float(posting["credit"]),
                currency=str(posting["currency"]),
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
                        "debit": float(posting["debit"]),
                        "credit": float(posting["credit"]),
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
                select(
                    JournalEntry.account_id,
                    func.sum(JournalEntry.debit),
                    func.sum(JournalEntry.credit),
                    Transaction.date,
                    Account.currency,
                )
                .join(Transaction, Transaction.id == JournalEntry.transaction_id)
                .join(Account, Account.id == JournalEntry.account_id)
            )
            if self.organization_id is not None:
                stmt = stmt.where(Account.organization_id == self.organization_id)
            if start_date is not None:
                stmt = stmt.where(Transaction.date >= start_date)
            if end_date is not None:
                stmt = stmt.where(Transaction.date <= end_date)
            stmt = stmt.group_by(JournalEntry.account_id, Transaction.date, Account.currency)
            for account_id, debit, credit, txn_date, acct_currency in self.s.exec(stmt):
                if account_id is None:
                    continue
                debit_dec = Decimal(str(debit or 0))
                credit_dec = Decimal(str(credit or 0))
                if currency and acct_currency and acct_currency != currency:
                    rate = (
                        self.s.exec(
                            select(Rate.value)
                            .where(Rate.base == acct_currency)
                            .where(Rate.quote == currency)
                            .where(Rate.date <= txn_date)
                            .order_by(Rate.date.desc())
                        ).first()
                        or None
                    )
                    if rate is None:
                        continue
                    factor = Decimal(str(rate))
                    debit_dec *= factor
                    credit_dec *= factor
                totals[int(account_id)]["debit"] += debit_dec
                totals[int(account_id)]["credit"] += credit_dec

        rows: list[TrialBalanceRow] = []
        account_map: dict[int, dict[str, Decimal]] = {}
        for account in accounts:
            if account.id is None:
                continue
            account_totals = totals.get(account.id, {"debit": Decimal("0"), "credit": Decimal("0")})
            debit = account_totals["debit"]
            credit = account_totals["credit"]
            balance = debit - credit
            rows.append(
                TrialBalanceRow(
                    account_id=int(account.id),
                    account_code=account.code,
                    account_name=account.name,
                    account_type=account.type,
                    currency=currency or account.currency,
                    debit=debit,
                    credit=credit,
                    balance=balance,
                )
            )
            account_map[int(account.id)] = {"debit": debit, "credit": credit, "net": balance}

        total_debit = sum((row.debit for row in rows), start=Decimal("0"))
        total_credit = sum((row.credit for row in rows), start=Decimal("0"))
        account_map["rows"] = rows  # type: ignore[index]
        account_map["total_debit"] = total_debit  # type: ignore[index]
        account_map["total_credit"] = total_credit  # type: ignore[index]
        return account_map


__all__ = ["LedgerService", "TrialBalanceRow"]
