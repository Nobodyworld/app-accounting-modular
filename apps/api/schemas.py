"""Pydantic schemas shared across the API surface."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from .models.models import AccountType
from .services.ledger_service import TrialBalanceRow

__all__ = [
    "AccountCreate",
    "ForecastRequest",
    "ForecastResponse",
    "Posting",
    "TransactionCreate",
    "TrialBalanceResponse",
    "TrialBalanceRowSchema",
]


class AccountCreate(BaseModel):
    """Payload for creating a ledger account."""

    name: str = Field(min_length=1)
    type: AccountType
    code: str | None = Field(default=None, max_length=64)
    currency: str = Field(default="USD", min_length=1, max_length=12)


class Posting(BaseModel):
    """Single debit/credit posting in a transaction."""

    account_id: int
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    currency: str | None = Field(default=None, max_length=12)

    @model_validator(mode="after")
    def validate_amounts(self) -> "Posting":
        if self.debit < 0 or self.credit < 0:
            raise ValueError("Debit and credit amounts must be non-negative")
        if self.debit and self.credit:
            raise ValueError("Specify either debit or credit, not both")
        if not self.debit and not self.credit:
            raise ValueError("Either debit or credit must be provided")
        return self

    def to_ledger_dict(self) -> dict[str, Any]:
        """Return a service-layer compatible dictionary payload."""

        return {
            "account_id": self.account_id,
            "debit": float(self.debit),
            "credit": float(self.credit),
            "currency": self.currency,
        }


class TransactionCreate(BaseModel):
    """Payload for posting a transaction to the general ledger."""

    date: date
    description: str = Field(min_length=1, max_length=255)
    postings: list[Posting]

    @field_validator("postings")
    @classmethod
    def ensure_balanced(
        cls, postings: list[Posting]
    ) -> list[Posting]:  # pragma: no cover - delegated validation
        debit_total = sum((p.debit for p in postings), start=Decimal("0"))
        credit_total = sum((p.credit for p in postings), start=Decimal("0"))
        if debit_total != credit_total:
            raise ValueError("Transaction is not balanced")
        return postings

    def ledger_payload(self) -> Iterable[dict[str, Any]]:
        """Yield posting dictionaries ready for :class:`LedgerService`."""

        return (posting.to_ledger_dict() for posting in self.postings)


class TrialBalanceRowSchema(BaseModel):
    """Serialized form of :class:`TrialBalanceRow`."""

    account_id: int
    account_code: str | None
    account_name: str
    account_type: AccountType
    currency: str
    debit: Decimal
    credit: Decimal
    balance: Decimal

    @classmethod
    def from_row(cls, row: TrialBalanceRow) -> "TrialBalanceRowSchema":
        return cls(
            account_id=row.account_id,
            account_code=row.account_code,
            account_name=row.account_name,
            account_type=row.account_type,
            currency=row.currency,
            debit=row.debit,
            credit=row.credit,
            balance=row.balance,
        )


class TrialBalanceResponse(BaseModel):
    """Response payload for trial balance requests."""

    rows: list[TrialBalanceRowSchema]
    total_debit: Decimal
    total_credit: Decimal

    @classmethod
    def from_service(
        cls, payload: dict[str, Any]
    ) -> "TrialBalanceResponse":
        rows = [TrialBalanceRowSchema.from_row(row) for row in payload["rows"]]
        return cls(
            rows=rows,
            total_debit=payload["total_debit"],
            total_credit=payload["total_credit"],
        )


class ForecastRequest(BaseModel):
    """Request body for forecast operations."""

    series: list[tuple[str | date, float]] = Field(default_factory=list)
    horizon: int = Field(default=30, ge=1)


class ForecastResponse(BaseModel):
    """Standardised forecast response."""

    forecast: list[tuple[str, float]]
    horizon: int
    order: tuple[int, int, int]
