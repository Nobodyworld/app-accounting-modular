"""SQLModel-powered persistence models for the public API."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, CheckConstraint, Column, Index, UniqueConstraint
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


class AccountingPeriodStatus(StrEnum):
    """Authoritative posting state for an inclusive accounting period."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"


class CloseCycleStatus(StrEnum):
    """Lifecycle states for the controlled close cycle."""

    DRAFT = "DRAFT"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    READY_FOR_APPROVAL = "READY_FOR_APPROVAL"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class CloseTaskStatus(StrEnum):
    PENDING = "PENDING"
    COMPLETE = "COMPLETE"


class CloseTaskControlType(StrEnum):
    SYSTEM = "SYSTEM"
    ATTESTATION = "ATTESTATION"
    ADMIN_APPROVAL = "ADMIN_APPROVAL"
    CUSTOM = "CUSTOM"


class ReconciliationStatus(StrEnum):
    UNSTARTED = "UNSTARTED"
    EXCEPTION = "EXCEPTION"
    IN_PROGRESS = "IN_PROGRESS"
    MATCHED = "MATCHED"
    APPROVED = "APPROVED"


class VarianceDisposition(StrEnum):
    UNRESOLVED = "UNRESOLVED"
    EXPLAINED = "EXPLAINED"
    TIMING = "TIMING"
    PERMANENT = "PERMANENT"
    CORRECTION_REQUIRED = "CORRECTION_REQUIRED"
    ACCEPTED = "ACCEPTED"


class JournalApprovalStatus(StrEnum):
    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"


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


class AuthSession(SQLModel, table=True):
    """Server-side authentication session and refresh-rotation state."""

    session_id: str = Field(primary_key=True, max_length=64)
    user_id: int = Field(foreign_key="user.id", index=True)
    current_refresh_jti_digest: str = Field(max_length=128)
    expires_at: datetime = Field(index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_rotated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    rotation_counter: int = Field(default=0, ge=0)
    revoked_at: datetime | None = Field(default=None, index=True)
    revocation_reason: str | None = Field(default=None, max_length=64)

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


class AccountingPeriod(SQLModel, table=True):
    """Tenant-scoped inclusive accounting period and posting lock."""

    id: int | None = Field(default=None, primary_key=True)
    organization_id: int = Field(foreign_key="organization.id", index=True)
    label: str = Field(max_length=120)
    start_date: date
    end_date: date
    status: AccountingPeriodStatus = Field(default=AccountingPeriodStatus.OPEN, index=True)
    version: int = Field(default=1, ge=1, le=2_147_483_647)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by_id: int | None = Field(default=None, foreign_key="user.id")
    updated_by_id: int | None = Field(default=None, foreign_key="user.id")
    closed_at: datetime | None = None
    closed_by_id: int | None = Field(default=None, foreign_key="user.id")
    reopened_at: datetime | None = None
    reopened_by_id: int | None = Field(default=None, foreign_key="user.id")

    __table_args__ = (
        UniqueConstraint("organization_id", "label", name="uq_accounting_period_org_label"),
        CheckConstraint("start_date <= end_date", name="ck_accounting_period_dates"),
        CheckConstraint("version >= 1", name="ck_accounting_period_version"),
        Index("ix_accounting_period_org_dates", "organization_id", "start_date", "end_date"),
        TABLE_KWARGS,
    )


class CloseCycle(SQLModel, table=True):
    """One controlled close lifecycle for an accounting period."""

    id: int | None = Field(default=None, primary_key=True)
    organization_id: int = Field(foreign_key="organization.id", index=True)
    period_id: int = Field(foreign_key="accountingperiod.id")
    name: str = Field(max_length=160)
    status: CloseCycleStatus = Field(default=CloseCycleStatus.DRAFT, index=True)
    owner_user_id: int | None = Field(default=None, foreign_key="user.id")
    due_date: date | None = None
    policy: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    notes: str | None = Field(default=None, max_length=4096)
    version: int = Field(default=1, ge=1, le=2_147_483_647)
    content_revision: int = Field(default=1, ge=1, le=2_147_483_647)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by_id: int | None = Field(default=None, foreign_key="user.id")
    updated_by_id: int | None = Field(default=None, foreign_key="user.id")
    started_at: datetime | None = None
    readiness_at: datetime | None = None
    approved_at: datetime | None = None
    closed_at: datetime | None = None
    cancelled_at: datetime | None = None
    reopened_at: datetime | None = None
    last_reason: str | None = Field(default=None, max_length=1000)

    __table_args__ = (
        UniqueConstraint("period_id", name="uq_close_cycle_period"),
        CheckConstraint("version >= 1", name="ck_close_cycle_version"),
        CheckConstraint("content_revision >= 1", name="ck_close_cycle_content_revision"),
        Index("ix_close_cycle_org_period", "organization_id", "period_id"),
        TABLE_KWARGS,
    )


class CloseChecklistTask(SQLModel, table=True):
    """Persisted deterministic or custom close checklist task."""

    id: int | None = Field(default=None, primary_key=True)
    organization_id: int = Field(foreign_key="organization.id", index=True)
    cycle_id: int = Field(foreign_key="closecycle.id")
    task_key: str = Field(max_length=120)
    title: str = Field(max_length=200)
    description: str = Field(default="", max_length=2000)
    category: str = Field(default="general", max_length=80)
    required: bool = True
    control_type: CloseTaskControlType = Field(default=CloseTaskControlType.CUSTOM)
    status: CloseTaskStatus = Field(default=CloseTaskStatus.PENDING)
    owner_user_id: int | None = Field(default=None, foreign_key="user.id")
    due_date: date | None = None
    completed_by_id: int | None = Field(default=None, foreign_key="user.id")
    completed_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)
    evidence_metadata: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    sort_order: int = Field(default=0, ge=0)
    version: int = Field(default=1, ge=1, le=2_147_483_647)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    __table_args__ = (
        UniqueConstraint("cycle_id", "task_key", name="uq_close_task_cycle_key"),
        Index("ix_close_task_org_cycle", "organization_id", "cycle_id"),
        TABLE_KWARGS,
    )


class AccountReconciliation(SQLModel, table=True):
    """Account-level reconciliation with server-computed ledger balance."""

    id: int | None = Field(default=None, primary_key=True)
    organization_id: int = Field(foreign_key="organization.id", index=True)
    cycle_id: int = Field(foreign_key="closecycle.id")
    account_id: int = Field(foreign_key="account.id")
    ledger_ending_balance: Decimal = Field(default=Decimal("0"), max_digits=20, decimal_places=4)
    control_balance: Decimal | None = Field(default=None, max_digits=20, decimal_places=4)
    difference: Decimal | None = Field(default=None, max_digits=20, decimal_places=4)
    tolerance: Decimal = Field(default=Decimal("0"), ge=0, max_digits=20, decimal_places=4)
    status: ReconciliationStatus = Field(default=ReconciliationStatus.UNSTARTED, index=True)
    owner_user_id: int | None = Field(default=None, foreign_key="user.id")
    prepared_by_id: int | None = Field(default=None, foreign_key="user.id")
    reviewer_user_id: int | None = Field(default=None, foreign_key="user.id")
    approved_by_id: int | None = Field(default=None, foreign_key="user.id")
    notes: str | None = Field(default=None, max_length=4096)
    evidence_metadata: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    prepared_at: datetime | None = None
    reviewed_at: datetime | None = None
    approved_at: datetime | None = None
    version: int = Field(default=1, ge=1, le=2_147_483_647)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    __table_args__ = (
        UniqueConstraint("cycle_id", "account_id", name="uq_reconciliation_cycle_account"),
        CheckConstraint("tolerance >= 0", name="ck_reconciliation_tolerance"),
        Index("ix_reconciliation_org_cycle", "organization_id", "cycle_id"),
        TABLE_KWARGS,
    )


class VarianceReview(SQLModel, table=True):
    """Materialized budget-report line and accountant disposition."""

    id: int | None = Field(default=None, primary_key=True)
    organization_id: int = Field(foreign_key="organization.id", index=True)
    cycle_id: int = Field(foreign_key="closecycle.id")
    budget_id: int = Field(foreign_key="budget.id")
    account_id: int = Field(foreign_key="account.id")
    period_start: date
    horizon: int
    budget_amount: Decimal = Field(max_digits=20, decimal_places=4)
    actual_amount: Decimal = Field(max_digits=20, decimal_places=4)
    variance_amount: Decimal = Field(max_digits=20, decimal_places=4)
    variance_percent: Decimal | None = Field(default=None, max_digits=20, decimal_places=6)
    absolute_threshold: Decimal = Field(default=Decimal("0"), ge=0, max_digits=20, decimal_places=4)
    percentage_threshold: Decimal | None = Field(default=None, ge=0, max_digits=20, decimal_places=6)
    is_material: bool = False
    disposition: VarianceDisposition = Field(default=VarianceDisposition.UNRESOLVED, index=True)
    owner_user_id: int | None = Field(default=None, foreign_key="user.id")
    reviewer_user_id: int | None = Field(default=None, foreign_key="user.id")
    note: str | None = Field(default=None, max_length=4096)
    reviewed_at: datetime | None = None
    report_metadata: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    version: int = Field(default=1, ge=1, le=2_147_483_647)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    __table_args__ = (
        UniqueConstraint("cycle_id", "budget_id", "account_id", "period_start", name="uq_variance_review_line"),
        Index("ix_variance_review_org_cycle", "organization_id", "cycle_id"),
        TABLE_KWARGS,
    )


class VarianceReviewRun(SQLModel, table=True):
    """Durable proof that the cycle's period-scoped variance control was executed."""

    id: int | None = Field(default=None, primary_key=True)
    organization_id: int = Field(foreign_key="organization.id", index=True)
    cycle_id: int = Field(foreign_key="closecycle.id")
    budget_id: int = Field(foreign_key="budget.id")
    horizon: int = Field(ge=1)
    absolute_threshold: Decimal = Field(default=Decimal("0"), ge=0, max_digits=20, decimal_places=4)
    percentage_threshold: Decimal | None = Field(default=None, ge=0, max_digits=20, decimal_places=6)
    report_parameters: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    report_provenance: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    generated_by_id: int = Field(foreign_key="user.id")
    row_count: int = Field(default=0, ge=0)
    content_revision: int = Field(ge=1)

    __table_args__ = (
        Index("ix_variance_review_run_org_cycle", "organization_id", "cycle_id"),
        TABLE_KWARGS,
    )


class JournalApproval(SQLModel, table=True):
    """Current approval state for one posted or staged journal reference."""

    id: int | None = Field(default=None, primary_key=True)
    organization_id: int = Field(foreign_key="organization.id", index=True)
    cycle_id: int = Field(foreign_key="closecycle.id")
    reference_key: str = Field(max_length=80)
    transaction_id: int | None = Field(default=None, foreign_key="transaction.id")
    staged_transaction_id: int | None = Field(default=None, foreign_key="stagedtransaction.id")
    requestor_user_id: int = Field(foreign_key="user.id")
    status: JournalApprovalStatus = Field(default=JournalApprovalStatus.REQUESTED, index=True)
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    decided_by_id: int | None = Field(default=None, foreign_key="user.id")
    decided_at: datetime | None = None
    reason: str | None = Field(default=None, max_length=2000)
    version: int = Field(default=1, ge=1, le=2_147_483_647)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    __table_args__ = (
        CheckConstraint(
            "(transaction_id IS NOT NULL AND staged_transaction_id IS NULL) OR "
            "(transaction_id IS NULL AND staged_transaction_id IS NOT NULL)",
            name="ck_journal_approval_one_reference",
        ),
        Index("ix_journal_approval_org_cycle", "organization_id", "cycle_id"),
        UniqueConstraint("cycle_id", "reference_key", name="uq_journal_approval_cycle_reference"),
        TABLE_KWARGS,
    )


class JournalApprovalDecision(SQLModel, table=True):
    """Append-only journal approval decision history."""

    id: int | None = Field(default=None, primary_key=True)
    organization_id: int = Field(foreign_key="organization.id", index=True)
    approval_id: int = Field(foreign_key="journalapproval.id")
    from_status: JournalApprovalStatus
    to_status: JournalApprovalStatus
    decided_by_id: int = Field(foreign_key="user.id")
    decided_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    reason: str | None = Field(default=None, max_length=2000)

    __table_args__ = (Index("ix_approval_decision_org_approval", "organization_id", "approval_id"), TABLE_KWARGS)


class CloseEvidence(SQLModel, table=True):
    """Metadata identifying a deterministic evidence snapshot."""

    id: int | None = Field(default=None, primary_key=True)
    organization_id: int = Field(foreign_key="organization.id", index=True)
    cycle_id: int = Field(foreign_key="closecycle.id")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    generated_by_id: int = Field(foreign_key="user.id")
    manifest_sha256: str = Field(max_length=64)
    # Kept as ``source_version`` for API compatibility. It stores the cycle's
    # authoritative content revision, not its lifecycle compare-and-swap version.
    source_version: int = Field(ge=1)
    is_final: bool = False
    summary: str | None = Field(default=None, max_length=1000)

    __table_args__ = (Index("ix_close_evidence_org_cycle", "organization_id", "cycle_id"), TABLE_KWARGS)
