from __future__ import annotations
"""Database models used across Modular Accounting services."""

from typing import Any, Optional
from enum import Enum
from datetime import date, datetime

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

__all__ = [
    "Account",
    "AccountType",
    "AuditAction",
    "AuditLog",
    "Country",
    "Event",
    "Instrument",
    "JournalEntry",
    "Price",
    "Rate",
    "Organization",
    "User",
    "TaxRule",
    "Transaction",
]


class AccountType(str, Enum):
    """Supported account categories."""

    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"


class TimestampedModel(SQLModel, table=False):
    """Mixin providing creation/update timestamps."""

    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)


class ActorTrackedModel(TimestampedModel, table=False):
    """Mixin adding provenance fields for actor/organization metadata."""

    created_by_id: Optional[int] = Field(default=None, foreign_key="user.id")
    updated_by_id: Optional[int] = Field(default=None, foreign_key="user.id")
    organization_id: Optional[int] = Field(default=None, foreign_key="organization.id")


class Organization(TimestampedModel, table=True):
    """Legal or logical organization that owns data within the system."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


class User(TimestampedModel, table=True):
    """End-user or system actor recorded for provenance."""

    id: Optional[int] = Field(default=None, primary_key=True)
    email: Optional[str] = Field(default=None, unique=True, index=True)
    name: Optional[str] = None
    organization_id: Optional[int] = Field(default=None, foreign_key="organization.id")


class Account(ActorTrackedModel, table=True):
    """Chart of accounts entry."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    code: Optional[str] = None
    type: AccountType
    currency: str = "USD"


class Transaction(ActorTrackedModel, table=True):
    """General ledger transaction."""

    id: Optional[int] = Field(default=None, primary_key=True)
    date: date
    description: str
    external_ref: Optional[str] = None


class JournalEntry(ActorTrackedModel, table=True):
    """Individual journal posting tied to a transaction."""

    id: Optional[int] = Field(default=None, primary_key=True)
    transaction_id: int = Field(foreign_key="transaction.id")
    account_id: int = Field(foreign_key="account.id")
    debit: float = 0.0
    credit: float = 0.0
    currency: str = "USD"


class Instrument(ActorTrackedModel, table=True):
    """Financial instrument reference data."""

    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str
    name: Optional[str] = None
    type: str = "equity"  # equity/etf/commodity/currency


class Price(ActorTrackedModel, table=True):
    """Daily close price for an instrument."""

    id: Optional[int] = Field(default=None, primary_key=True)
    instrument_id: int = Field(foreign_key="instrument.id")
    date: date
    close: float
    provider: str


class Rate(ActorTrackedModel, table=True):
    """Foreign exchange rate observation."""

    id: Optional[int] = Field(default=None, primary_key=True)
    base: str
    quote: str
    date: date
    value: float
    provider: str


class Country(ActorTrackedModel, table=True):
    """Geopolitical country reference."""

    id: Optional[int] = Field(default=None, primary_key=True)
    iso2: str
    name: str


class TaxRule(ActorTrackedModel, table=True):
    """Machine-readable tax rule."""

    id: Optional[int] = Field(default=None, primary_key=True)
    jurisdiction: str  # e.g., US-FED, EU-IE
    scope: str  # e.g., vat, corporate_income, payroll
    expression: str  # JSONLogic or simple expr string
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    source: Optional[str] = None


class Event(ActorTrackedModel, table=True):
    """External event for market intelligence."""

    id: Optional[int] = Field(default=None, primary_key=True)
    ts: datetime
    source: str
    title: str
    score: Optional[float] = None  # relevance/intensity


class AuditAction(str, Enum):
    """Enumerated audit event types."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class AuditLog(SQLModel, table=True):
    """Immutable append-only audit trail capturing entity lifecycle events."""

    id: Optional[int] = Field(default=None, primary_key=True)
    ts: datetime = Field(default_factory=datetime.utcnow, nullable=False, index=True)
    action: AuditAction
    entity_name: str
    entity_id: Optional[str] = Field(default=None, index=True)
    before_state: Optional[dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    after_state: Optional[dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    payload_diff: Optional[dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    request_id: Optional[str] = Field(default=None, index=True)
    actor_user_id: Optional[int] = Field(default=None, foreign_key="user.id", index=True)
    actor_org_id: Optional[int] = Field(
        default=None, foreign_key="organization.id", index=True
    )
    actor_label: Optional[str] = None
    source: Optional[str] = None
    context: Optional[dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )

