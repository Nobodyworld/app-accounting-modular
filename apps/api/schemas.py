"""Pydantic schemas shared across the API surface."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models.models import AccountType, WorkflowStatus
from .services.ledger_service import TrialBalanceRow
from .services.workflow_service import WorkflowResult

__all__ = [
    "AccountCreate",
    "BudgetReportLineSchema",
    "BudgetReportResponse",
    "CashflowForecastResponse",
    "ForecastRequest",
    "ForecastResponse",
    "ReportMetadata",
    "Posting",
    "TransactionCreate",
    "TrialBalanceResponse",
    "TrialBalanceRowSchema",
    "WorkflowIngestRequest",
    "WorkflowIngestResponse",
    "WorkflowProcessRequest",
    "WorkflowResultSchema",
    "StagedPostingIngest",
    "StagedPostingRead",
    "StagedTransactionIngest",
    "StagedTransactionRead",
]


class AccountCreate(BaseModel):
    """Payload for creating a ledger account."""

    name: str = Field(min_length=1)
    type: AccountType
    code: str | None = Field(default=None, max_length=64)
    currency: str = Field(default="USD", min_length=1, max_length=12)
    organization_id: int


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
    organization_id: int

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


class StagedPostingIngest(BaseModel):
    """Posting payload accepted by the staging workflow."""

    account_id: int | None = None
    account_code: str | None = None
    account_name: str | None = None
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")
    currency: str | None = Field(default=None, max_length=12)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_account_reference(self) -> "StagedPostingIngest":
        if self.account_id is None and not (self.account_code or self.account_name):
            raise ValueError("account reference is required")
        return self


class StagedTransactionIngest(BaseModel):
    """Transaction ingestion payload."""

    date: date
    description: str = Field(min_length=1, max_length=255)
    postings: list[StagedPostingIngest]
    source_reference: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("postings")
    @classmethod
    def ensure_postings(cls, postings: list[StagedPostingIngest]) -> list[StagedPostingIngest]:
        if not postings:
            raise ValueError("at least one posting is required")
        return postings


class WorkflowIngestRequest(BaseModel):
    """Request body for staging transactions."""

    source: str = Field(default="api", min_length=1)
    source_reference: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    transactions: list[StagedTransactionIngest]
    auto_process: bool = True

    @field_validator("transactions")
    @classmethod
    def ensure_transactions(
        cls, transactions: list[StagedTransactionIngest]
    ) -> list[StagedTransactionIngest]:
        if not transactions:
            raise ValueError("no transactions supplied")
        return transactions


class WorkflowResultSchema(BaseModel):
    """Outcome summary returned by the workflow service."""

    staged_transaction_id: int
    status: WorkflowStatus
    transaction_id: int | None = None
    validation_errors: list[str] | None = None

    @classmethod
    def from_result(cls, result: WorkflowResult) -> "WorkflowResultSchema":
        return cls(
            staged_transaction_id=result.staged_transaction_id,
            status=result.status,
            transaction_id=result.transaction_id,
            validation_errors=result.validation_errors,
        )


class WorkflowIngestResponse(BaseModel):
    """Response payload for ingestion requests."""

    staged_ids: list[int]
    results: list[WorkflowResultSchema] = Field(default_factory=list)


class WorkflowProcessRequest(BaseModel):
    """Request body to trigger processing of staged transactions."""

    staged_ids: list[int] | None = None
    auto_post: bool = True


class StagedPostingRead(BaseModel):
    """Serialized staged posting."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int | None
    account_code: str | None
    account_name: str | None
    debit: Decimal
    credit: Decimal
    currency: str | None
    metadata: dict[str, Any]


class StagedTransactionRead(BaseModel):
    """Serialized staged transaction with postings."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    date: date
    description: str
    status: WorkflowStatus
    source: str
    source_reference: str | None
    source_metadata: dict[str, Any]
    validation_errors: list[str] | None
    transaction_id: int | None
    ingested_at: datetime
    updated_at: datetime
    postings: list[StagedPostingRead]


class ForecastRequest(BaseModel):
    """Request body for forecast operations."""

    series: list[tuple[str | date, float]] = Field(default_factory=list)
    horizon: int = Field(default=30, ge=1)
    organization_id: int


class ForecastResponse(BaseModel):
    """Standardised forecast response."""

    forecast: list[tuple[str, float]]
    horizon: int
    order: tuple[int, int, int]


class ReportMetadata(BaseModel):
    """Metadata accompanying generated reports."""

    generated_at: datetime
    horizon: int | None = None
    plan_id: int | None = None
    budget_id: int | None = None
    organization_id: int | None = None


class BudgetReportLineSchema(BaseModel):
    """Single row within a budget vs actual report."""

    account_id: int
    account_code: str | None = None
    account_name: str
    period_start: date
    budget_amount: float
    actual_amount: float
    variance: float
    burn_rate: float | None = None
    forecast: list[tuple[str, float]] = Field(default_factory=list)


class BudgetReportResponse(BaseModel):
    """Serialized response for budget vs actual outputs."""

    lines: list[BudgetReportLineSchema]
    summary: dict[str, float | None]
    metadata: ReportMetadata
    csv_export: str


class CashflowForecastResponse(BaseModel):
    """Serialized response for cashflow forecasts."""

    historical: list[dict[str, float | str]]
    forecast: list[tuple[str, float]]
    model_order: tuple[int, int, int]
    metadata: ReportMetadata
    current_cash: float
    average_monthly_flow: float | None = None
    csv_export: str
