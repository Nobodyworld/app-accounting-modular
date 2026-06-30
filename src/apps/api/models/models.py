"""SQLModel-powered persistence models for the public API."""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Column, Index, UniqueConstraint
from sqlmodel import Field, SQLModel

TABLE_KWARGS: dict[str, object] = {"extend_existing": True}


class AccountType(StrEnum):
    """Enumerates supported account classifications."""

    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"


class WorkflowStatus(StrEnum):
    """Lifecycle status for staged workflow transactions."""

    INGESTED = "INGESTED"
    VALIDATED = "VALIDATED"
    POSTED = "POSTED"
    FAILED = "FAILED"


class Organization(SQLModel, table=True):
    """Tenant/organization metadata."""

    id: int | None = Field(default=None, primary_key=True)
    name: str
    is_active: bool = True
    created_at: datetime | None = Field(default=None)
    updated_at: datetime | None = Field(default=None)

    __table_args__ = TABLE_KWARGS


class User(SQLModel, table=True):
    """Application user participating in organisations."""

    id: int | None = Field(default=None, primary_key=True)
    email: str
    password_hash: str
    name: str | None = None
    organization_id: int | None = Field(default=None, foreign_key="organization.id")
    is_active: bool = True
    created_at: datetime | None = Field(default=None)
    updated_at: datetime | None = Field(default=None)

    __table_args__ = TABLE_KWARGS


class Membership(SQLModel, table=True):
    """Associates a user with an organization and permissions."""

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    organization_id: int = Field(foreign_key="organization.id")
    is_admin: bool = False
    can_manage_ledger: bool = False
    can_manage_fx: bool = False
    can_manage_market: bool = False
    can_manage_tax: bool = False

    __table_args__ = (UniqueConstraint("user_id", "organization_id", name="uq_membership_user_org"), TABLE_KWARGS)


class Account(SQLModel, table=True):
    """Chart-of-accounts entry supporting optional display codes."""

    id: int | None = Field(default=None, primary_key=True)
    organization_id: int | None = Field(default=None, foreign_key="organization.id")
    name: str
    code: str | None = None
    type: AccountType
    currency: str = "USD"

    __table_args__ = (UniqueConstraint("organization_id", "code", name="uq_account_org_code"), TABLE_KWARGS)


class Transaction(SQLModel, table=True):
    """Financial transaction describing journal entry context."""

    id: int | None = Field(default=None, primary_key=True)
    organization_id: int | None = Field(default=None, foreign_key="organization.id")
    date: date
    description: str
    external_ref: str | None = None

    __table_args__ = TABLE_KWARGS


class JournalEntry(SQLModel, table=True):
    """Double-entry bookkeeping line item for a transaction."""

    id: int | None = Field(default=None, primary_key=True)
    transaction_id: int = Field(foreign_key="transaction.id")
    account_id: int = Field(foreign_key="account.id")
    debit: float = 0.0
    credit: float = 0.0
    currency: str = "USD"

    __table_args__ = TABLE_KWARGS


class Instrument(SQLModel, table=True):
    """Tradable instrument metadata for price lookups."""

    id: int | None = Field(default=None, primary_key=True)
    organization_id: int | None = Field(default=None, foreign_key="organization.id")
    symbol: str
    name: str | None = None
    type: str = "equity"  # equity/etf/commodity/currency

    __table_args__ = TABLE_KWARGS


class Price(SQLModel, table=True):
    """Historical price observation for an instrument."""

    id: int | None = Field(default=None, primary_key=True)
    instrument_id: int = Field(foreign_key="instrument.id")
    date: date
    close: float
    provider: str

    __table_args__ = (
        UniqueConstraint("instrument_id", "date", "provider", name="uq_price_instrument_date_provider"),
        TABLE_KWARGS,
    )


class Rate(SQLModel, table=True):
    """Foreign exchange rate observation."""

    id: int | None = Field(default=None, primary_key=True)
    base: str
    quote: str
    date: date
    value: float
    provider: str

    __table_args__ = (
        UniqueConstraint("base", "quote", "date", "provider", name="uq_rate_base_quote_date_provider"),
        Index("ix_rate_base_quote_date_provider", "base", "quote", "date", "provider"),
        TABLE_KWARGS,
    )


class Country(SQLModel, table=True):
    """Country metadata including ISO codes."""

    id: int | None = Field(default=None, primary_key=True)
    iso2: str
    name: str

    __table_args__ = TABLE_KWARGS


class TaxRule(SQLModel, table=True):
    """Configured tax rule definition stored for orchestration."""

    id: int | None = Field(default=None, primary_key=True)
    organization_id: int | None = Field(default=None, foreign_key="organization.id")
    jurisdiction: str  # e.g., US-FED, EU-IE
    scope: str  # e.g., vat, corporate_income, payroll
    expression: str  # JSONLogic or simple expr string
    valid_from: date | None = None
    valid_to: date | None = None
    source: str | None = None
    precedence: int = Field(default=100)
    rule_metadata: dict[str, Any] | None = Field(default=None, sa_column=Column("metadata", JSON))

    __table_args__ = TABLE_KWARGS


class Event(SQLModel, table=True):
    """Forecast-relevant event used for metadata enrichment."""

    id: int | None = Field(default=None, primary_key=True)
    organization_id: int | None = Field(default=None, foreign_key="organization.id")
    ts: datetime
    source: str
    title: str
    score: float | None = None  # relevance/intensity

    __table_args__ = TABLE_KWARGS


class AuditAction(StrEnum):
    """Enumerates audit log action types."""

    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    ACCESS = "ACCESS"


class AuditLog(SQLModel, table=True):
    """Immutable audit trail entry."""

    id: int | None = Field(default=None, primary_key=True)
    ts: datetime
    action: AuditAction
    entity_name: str
    entity_id: str | None = None
    before_state: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    after_state: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    payload_diff: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    request_id: str
    actor_user_id: int | None = None
    actor_org_id: int | None = None
    actor_label: str | None = None
    source: str | None = None
    context: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))

    __table_args__ = TABLE_KWARGS


class Budget(SQLModel, table=True):
    """Budget header capturing scope and period."""

    id: int | None = Field(default=None, primary_key=True)
    organization_id: int = Field(foreign_key="organization.id")
    name: str
    start_date: date
    end_date: date
    currency: str = "USD"
    created_at: datetime | None = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime | None = Field(default_factory=lambda: datetime.now(UTC))

    __table_args__ = TABLE_KWARGS


class BudgetLine(SQLModel, table=True):
    """Budgeted amount for an account and period."""

    id: int | None = Field(default=None, primary_key=True)
    budget_id: int = Field(foreign_key="budget.id")
    account_id: int = Field(foreign_key="account.id")
    period_start: date
    amount: float

    __table_args__ = (UniqueConstraint("budget_id", "account_id", "period_start", name="uq_budget_line"), TABLE_KWARGS)


class ForecastPlan(SQLModel, table=True):
    """A forecast configuration for a budget or organization."""

    id: int | None = Field(default=None, primary_key=True)
    organization_id: int = Field(foreign_key="organization.id")
    budget_id: int | None = Field(default=None, foreign_key="budget.id")
    name: str
    horizon: int
    is_active: bool = True
    refresh_interval_minutes: int = Field(default=360)
    last_refreshed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    __table_args__ = (
        UniqueConstraint("organization_id", "budget_id", "name", name="uq_plan_scope_name"),
        TABLE_KWARGS,
    )


class ForecastOutput(SQLModel, table=True):
    """Persisted forecast or report output for reuse."""

    id: int | None = Field(default=None, primary_key=True)
    plan_id: int = Field(foreign_key="forecastplan.id")
    report_type: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    summary: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    context: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    csv_data: str | None = None

    __table_args__ = TABLE_KWARGS


class StagedTransaction(SQLModel, table=True):
    """Transaction awaiting validation and posting."""

    id: int | None = Field(default=None, primary_key=True)
    date: date
    description: str
    source: str
    source_reference: str | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    status: WorkflowStatus = Field(default=WorkflowStatus.INGESTED)
    transaction_id: int | None = None
    validation_errors: list[str] | None = Field(default=None, sa_column=Column(JSON))
    ingest_diagnostics: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    __table_args__ = TABLE_KWARGS


class StagedPosting(SQLModel, table=True):
    """Posting tied to a staged transaction."""

    id: int | None = Field(default=None, primary_key=True)
    staged_transaction_id: int = Field(foreign_key="stagedtransaction.id")
    account_id: int | None = None
    account_code: str | None = None
    account_name: str | None = None
    debit: float = 0.0
    credit: float = 0.0
    currency: str | None = None
    context: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    __table_args__ = TABLE_KWARGS
