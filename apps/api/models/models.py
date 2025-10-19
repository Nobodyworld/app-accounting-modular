"""Database models used across Modular Accounting services."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

from sqlalchemy import Column, JSON, Text, func
from sqlmodel import Field, SQLModel

__all__ = [
    "Account",
    "AccountType",
    "AuditAction",
    "AuditLog",
    "Budget",
    "BudgetLine",
    "Country",
    "Event",
    "ForecastOutput",
    "ForecastPlan",
    "Instrument",
    "JournalEntry",
    "Membership",
    "Organization",
    "Price",
    "Rate",
    "StagedPosting",
    "StagedTransaction",
    "TaxRule",
    "Transaction",
    "User",
    "WorkflowStatus",
]


class TimestampMixin(SQLModel, table=False):
    """Common auditing columns for mutable tables."""

    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        nullable=False,
        sa_column_kwargs={"server_default": func.now()},
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        nullable=False,
        sa_column_kwargs={"server_default": func.now(), "onupdate": func.now()},
    )


class ActorTrackedModel(TimestampMixin, table=False):
    """Mixin adding provenance fields for actor/organization metadata."""

    created_by_id: Optional[int] = Field(default=None, foreign_key="user.id")
    updated_by_id: Optional[int] = Field(default=None, foreign_key="user.id")
    organization_id: Optional[int] = Field(
        default=None, foreign_key="organization.id", index=True
    )


class Organization(TimestampMixin, SQLModel, table=True):
    """Tenant container for isolated accounting data."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    is_active: bool = Field(default=True)


class User(TimestampMixin, SQLModel, table=True):
    """Application user with hashed credentials."""

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    full_name: Optional[str] = None
    password_hash: str
    is_active: bool = Field(default=True)


class Membership(TimestampMixin, SQLModel, table=True):
    """Association between users and organizations with permissions."""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    organization_id: int = Field(foreign_key="organization.id", index=True)
    role: str = Field(default="member")
    is_admin: bool = Field(default=False)
    can_manage_ledger: bool = Field(default=False)
    can_manage_fx: bool = Field(default=False)
    can_manage_market: bool = Field(default=False)
    can_manage_tax: bool = Field(default=False)


class AccountType(str, Enum):
    """Supported account categories."""

    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"


class Account(ActorTrackedModel, table=True):
    """Chart of accounts entry."""

    id: Optional[int] = Field(default=None, primary_key=True)
    organization_id: Optional[int] = Field(
        default=None, foreign_key="organization.id", index=True
    )
    name: str
    code: Optional[str] = Field(default=None, max_length=64, index=True)
    type: AccountType
    currency: str = Field(default="USD", max_length=12)


class Transaction(ActorTrackedModel, table=True):
    """General ledger transaction."""

    id: Optional[int] = Field(default=None, primary_key=True)
    organization_id: Optional[int] = Field(
        default=None, foreign_key="organization.id", index=True
    )
    date: date
    description: str
    external_ref: Optional[str] = Field(default=None, max_length=255)


class JournalEntry(ActorTrackedModel, table=True):
    """Individual journal posting tied to a transaction."""

    id: Optional[int] = Field(default=None, primary_key=True)
    organization_id: Optional[int] = Field(
        default=None, foreign_key="organization.id", index=True
    )
    transaction_id: int = Field(foreign_key="transaction.id")
    account_id: int = Field(foreign_key="account.id")
    debit: float = 0.0
    credit: float = 0.0
    currency: str = Field(default="USD", max_length=12)


class Budget(SQLModel, table=True):
    """Operating budget for an organization."""

    id: Optional[int] = Field(default=None, primary_key=True)
    organization_id: int = Field(foreign_key="organization.id")
    name: str
    start_date: date
    end_date: date
    currency: str = Field(default="USD", max_length=12)


class BudgetLine(SQLModel, table=True):
    """Budgeted amount for an account and period."""

    id: Optional[int] = Field(default=None, primary_key=True)
    budget_id: int = Field(foreign_key="budget.id")
    account_id: int = Field(foreign_key="account.id")
    period_start: date
    amount: float


class ForecastPlan(SQLModel, table=True):
    """Configuration describing how forecasts are generated."""

    id: Optional[int] = Field(default=None, primary_key=True)
    organization_id: int = Field(foreign_key="organization.id")
    budget_id: Optional[int] = Field(default=None, foreign_key="budget.id")
    name: str
    horizon: int
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    # TODO - Enforce uniqueness on (organization_id, name) to prevent duplicates.


class ForecastOutput(SQLModel, table=True):
    """Stored forecast artefact for quick retrieval."""

    id: Optional[int] = Field(default=None, primary_key=True)
    plan_id: int = Field(foreign_key="forecastplan.id")
    report_type: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    summary: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    context: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    csv_data: Optional[str] = Field(default=None, sa_column=Column(Text))


class Instrument(ActorTrackedModel, table=True):
    """Financial instrument reference data."""

    id: Optional[int] = Field(default=None, primary_key=True)
    organization_id: Optional[int] = Field(
        default=None, foreign_key="organization.id", index=True
    )
    symbol: str
    name: Optional[str] = None
    type: str = Field(default="equity", max_length=32)


class Price(ActorTrackedModel, table=True):
    """Daily close price for an instrument."""

    id: Optional[int] = Field(default=None, primary_key=True)
    instrument_id: int = Field(foreign_key="instrument.id")
    organization_id: Optional[int] = Field(
        default=None, foreign_key="organization.id", index=True
    )
    date: date
    close: float
    provider: str
    # TODO - Add unique constraint on (instrument_id, date, provider) to avoid duplicates.


class Rate(ActorTrackedModel, table=True):
    """Foreign exchange rate observation."""

    id: Optional[int] = Field(default=None, primary_key=True)
    organization_id: Optional[int] = Field(
        default=None, foreign_key="organization.id", index=True
    )
    base: str
    quote: str
    date: date
    value: float
    provider: str
    # TODO - Create composite index covering base/quote/date/provider for lookups.


class Country(ActorTrackedModel, table=True):
    """Geopolitical country reference."""

    id: Optional[int] = Field(default=None, primary_key=True)
    iso2: str
    name: str


class TaxRule(ActorTrackedModel, table=True):
    """Machine-readable tax rule."""

    id: Optional[int] = Field(default=None, primary_key=True)
    organization_id: Optional[int] = Field(
        default=None, foreign_key="organization.id", index=True
    )
    jurisdiction: str
    scope: str
    expression: str
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    source: Optional[str] = None


class Event(ActorTrackedModel, table=True):
    """External event for market intelligence."""

    id: Optional[int] = Field(default=None, primary_key=True)
    organization_id: Optional[int] = Field(
        default=None, foreign_key="organization.id", index=True
    )
    ts: datetime
    source: str
    title: str
    score: Optional[float] = None


class AuditAction(str, Enum):
    """Enumerated audit event types."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    ACCESS = "access"


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
    # TODO - Consider table partitioning/retention policies for long-term growth.


class WorkflowStatus(str, Enum):
    """Processing state for staged transactions."""

    INGESTED = "INGESTED"
    VALIDATED = "VALIDATED"
    POSTED = "POSTED"
    FAILED = "FAILED"


class StagedTransaction(SQLModel, table=True):
    """Workflow-controlled transaction awaiting validation/posting."""

    id: Optional[int] = Field(default=None, primary_key=True)
    date: date
    description: str
    status: WorkflowStatus = Field(default=WorkflowStatus.INGESTED)
    source: str = Field(default="unknown")
    source_reference: Optional[str] = None
    source_metadata: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    validation_errors: Optional[list[str]] = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    transaction_id: Optional[int] = Field(default=None, foreign_key="transaction.id")
    ingested_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class StagedPosting(SQLModel, table=True):
    """Individual staging record for a transaction posting."""

    id: Optional[int] = Field(default=None, primary_key=True)
    staged_transaction_id: int = Field(foreign_key="stagedtransaction.id")
    account_id: Optional[int] = None
    account_code: Optional[str] = None
    account_name: Optional[str] = None
    debit: float = 0.0
    credit: float = 0.0
    currency: Optional[str] = None
    context: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
