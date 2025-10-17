from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Sequence

from pydantic import BaseModel, Field, field_validator, model_validator

from .models.models import AccountType


class AccountCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    type: AccountType
    code: str | None = Field(default=None, max_length=50)
    currency: str = Field(default="USD", min_length=1, max_length=12)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty")
        return value

    @field_validator("code")
    @classmethod
    def _normalise_code(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("currency")
    @classmethod
    def _normalise_currency(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("currency must not be empty")
        return value


class AccountRead(BaseModel):
    id: int
    name: str
    code: str | None
    type: AccountType
    currency: str

    model_config = {"from_attributes": True}


class TransactionPosting(BaseModel):
    account_id: int
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    currency: str | None = Field(default=None, max_length=12)

    @model_validator(mode="after")
    def _validate_amounts(self) -> "TransactionPosting":
        debit = self.debit
        credit = self.credit
        if debit < 0 or credit < 0:
            raise ValueError("debit and credit must be non-negative")
        if debit == 0 and credit == 0:
            raise ValueError("either debit or credit must be provided")
        if debit != 0 and credit != 0:
            raise ValueError("provide only one of debit or credit")
        return self

    @field_validator("currency")
    @classmethod
    def _normalise_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        return value or None


class TransactionCreate(BaseModel):
    date: date
    description: str = Field(..., min_length=1)
    postings: Sequence[TransactionPosting]
    external_ref: str | None = Field(default=None, max_length=255)

    @field_validator("description")
    @classmethod
    def _strip_description(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("description must not be empty")
        return value

    @model_validator(mode="after")
    def _validate_postings(self) -> "TransactionCreate":
        if len(self.postings) < 2:
            raise ValueError("transactions must include at least two postings")
        return self


class TransactionRead(BaseModel):
    id: int
    date: date
    description: str
    external_ref: str | None

    model_config = {"from_attributes": True}


class TrialBalanceRowSchema(BaseModel):
    account_id: int
    account_code: str | None
    account_name: str
    account_type: AccountType
    currency: str
    debit: Decimal
    credit: Decimal
    balance: Decimal

    model_config = {"from_attributes": True}


class TrialBalanceResponse(BaseModel):
    rows: list[TrialBalanceRowSchema]
    total_debit: Decimal
    total_credit: Decimal


class ForecastPoint(BaseModel):
    timestamp: datetime
    value: float


class ForecastRequest(BaseModel):
    series: Sequence[ForecastPoint]
    horizon: int = Field(default=30, ge=1, le=365)


class ForecastResponse(BaseModel):
    forecast: list[tuple[str, float]]
    horizon: int
    order: tuple[int, int, int]


__all__ = [
    "AccountCreate",
    "AccountRead",
    "TransactionPosting",
    "TransactionCreate",
    "TransactionRead",
    "TrialBalanceRowSchema",
    "TrialBalanceResponse",
    "ForecastPoint",
    "ForecastRequest",
    "ForecastResponse",
]
