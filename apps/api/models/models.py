from __future__ import annotations
"""Database models used across Modular Accounting services."""

from typing import Any, Optional
from enum import Enum
from datetime import date, datetime

from sqlalchemy import Column, JSON
# todo - fix
from sqlalchemy import Column, JSON, Text
from sqlalchemy import func
from sqlmodel import Field, SQLModel

__all__ = [
    "Organization",
    "User",
    "Membership",
    "Account",
    "AccountType",
  # todo - fix
    "AuditAction",
    "AuditLog",
    "Budget",
    "BudgetLine",
    "Country",
    "Event",
  # todo - fix
    "ForecastOutput",
    "ForecastPlan",
    "StagedPosting",
    "StagedTransaction",
    "WorkflowStatus",
    "Instrument",
    "JournalEntry",
    "Organization",
    "Price",
    "Rate",
    "Organization",
    "User",
    "TaxRule",
    "Transaction",
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

# todo - fix
class Organization(SQLModel, table=True):
    """Legal entity or business unit tracked in the system."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


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
class Account(SQLModel, table=True):
class Account(TimestampMixin, SQLModel, table=True):
    """Chart of accounts entry."""

    id: Optional[int] = Field(default=None, primary_key=True)
    organization_id: int | None = Field(
        default=None, foreign_key="organization.id", index=True, nullable=False
    )
    name: str
    code: Optional[str] = None
    type: AccountType
    currency: str = "USD"
    organization_id: Optional[int] = Field(default=None, foreign_key="organization.id")


class Transaction(ActorTrackedModel, table=True):
class Transaction(TimestampMixin, SQLModel, table=True):
    """General ledger transaction."""

    id: Optional[int] = Field(default=None, primary_key=True)
    organization_id: int | None = Field(
        default=None, foreign_key="organization.id", index=True, nullable=False
    )
    date: date
    description: str
    external_ref: Optional[str] = None


class JournalEntry(ActorTrackedModel, table=True):
class JournalEntry(TimestampMixin, SQLModel, table=True):
    """Individual journal posting tied to a transaction."""

    id: Optional[int] = Field(default=None, primary_key=True)
    organization_id: int | None = Field(
        default=None, foreign_key="organization.id", index=True, nullable=False
    )
    transaction_id: int = Field(foreign_key="transaction.id")
    account_id: int = Field(foreign_key="account.id")
    debit: float = 0.0
    credit: float = 0.0
    currency: str = "USD"

# todo - fix
class Budget(SQLModel, table=True):
    """Operating budget for an organization."""

    id: Optional[int] = Field(default=None, primary_key=True)
    organization_id: int = Field(foreign_key="organization.id")
    name: str
    start_date: date
    end_date: date
    currency: str = "USD"


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


class ForecastOutput(SQLModel, table=True):
    """Stored forecast artefact for quick retrieval."""

    id: Optional[int] = Field(default=None, primary_key=True)
    plan_id: int = Field(foreign_key="forecastplan.id")
    report_type: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    summary: dict | None = Field(default=None, sa_column=Column(JSON))
    context: dict | None = Field(default=None, sa_column=Column(JSON))
    csv_data: Optional[str] = Field(default=None, sa_column=Column(Text))


class Instrument(ActorTrackedModel, table=True):
class Instrument(SQLModel, table=True):
class Instrument(TimestampMixin, SQLModel, table=True):
    """Financial instrument reference data."""

    id: Optional[int] = Field(default=None, primary_key=True)
    organization_id: int | None = Field(
        default=None, foreign_key="organization.id", index=True, nullable=False
    )
    symbol: str
    name: Optional[str] = None
    type: str = "equity"  # equity/etf/commodity/currency


class Price(ActorTrackedModel, table=True):
class Price(TimestampMixin, SQLModel, table=True):
    """Daily close price for an instrument."""

    id: Optional[int] = Field(default=None, primary_key=True)
    instrument_id: int = Field(foreign_key="instrument.id")
    organization_id: int | None = Field(
        default=None, foreign_key="organization.id", index=True, nullable=False
    )
    date: date
    close: float
    provider: str


class Rate(ActorTrackedModel, table=True):
class Rate(TimestampMixin, SQLModel, table=True):
    """Foreign exchange rate observation."""

    id: Optional[int] = Field(default=None, primary_key=True)
    organization_id: int | None = Field(
        default=None, foreign_key="organization.id", index=True, nullable=False
    )
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
class TaxRule(TimestampMixin, SQLModel, table=True):
    """Machine-readable tax rule."""

    id: Optional[int] = Field(default=None, primary_key=True)
    organization_id: int | None = Field(
        default=None, foreign_key="organization.id", index=True, nullable=False
    )
    jurisdiction: str  # e.g., US-FED, EU-IE
    scope: str  # e.g., vat, corporate_income, payroll
    expression: str  # JSONLogic or simple expr string
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    source: Optional[str] = None


class Event(ActorTrackedModel, table=True):
class Event(TimestampMixin, SQLModel, table=True):
    """External event for market intelligence."""

    id: Optional[int] = Field(default=None, primary_key=True)
    organization_id: int | None = Field(
        default=None, foreign_key="organization.id", index=True, nullable=False
    )
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

