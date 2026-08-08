"""Typed request and response contracts for the accountant close API."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .limits import (
    MAX_APPROVAL_COMMENT_LENGTH,
    MAX_CHECKLIST_DESCRIPTION_LENGTH,
    MAX_CHECKLIST_NOTES_LENGTH,
    MAX_CHECKLIST_TITLE_LENGTH,
    MAX_CLOSE_NAME_LENGTH,
    MAX_CLOSE_NOTES_LENGTH,
    MAX_PERIOD_LABEL_LENGTH,
    MAX_RECONCILIATION_NOTES_LENGTH,
    MAX_TRANSITION_REASON_LENGTH,
)
from .metadata_limits import validate_metadata
from .models.models import (
    AccountingPeriodStatus,
    CloseCycleStatus,
    CloseTaskControlType,
    CloseTaskStatus,
    JournalApprovalStatus,
    ReconciliationStatus,
    VarianceDisposition,
)
from .services.close_evidence_service import EvidenceBundle
from .services.close_service import CloseReadiness


class OrmSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PeriodCreate(BaseModel):
    label: str = Field(min_length=1, max_length=MAX_PERIOD_LABEL_LENGTH)
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_dates(self) -> PeriodCreate:
        if self.start_date > self.end_date:
            raise ValueError("start_date must not be after end_date")
        return self


class PeriodRead(OrmSchema):
    id: int
    organization_id: int
    label: str
    start_date: date
    end_date: date
    status: AccountingPeriodStatus
    version: int
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    reopened_at: datetime | None


class CycleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=MAX_CLOSE_NAME_LENGTH)
    owner_user_id: int | None = Field(default=None, ge=1)
    due_date: date | None = None
    policy: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=MAX_CLOSE_NOTES_LENGTH)

    @field_validator("policy")
    @classmethod
    def bounded_policy(cls, value: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], validate_metadata(value))


class CycleRead(OrmSchema):
    id: int
    organization_id: int
    period_id: int
    name: str
    status: CloseCycleStatus
    owner_user_id: int | None
    due_date: date | None
    policy: dict[str, Any]
    notes: str | None
    version: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    readiness_at: datetime | None
    approved_at: datetime | None
    closed_at: datetime | None
    cancelled_at: datetime | None
    reopened_at: datetime | None
    last_reason: str | None


class VersionRequest(BaseModel):
    version: int = Field(ge=1)


class ReasonedTransitionRequest(VersionRequest):
    reason: str = Field(min_length=1, max_length=MAX_TRANSITION_REASON_LENGTH)


class ReadinessBlockerSchema(BaseModel):
    code: str
    category: str
    message: str
    source_entity_type: str
    source_entity_id: str | None
    recommended_action: str


class ReadinessResponse(BaseModel):
    cycle_id: int
    cycle_status: CloseCycleStatus
    period_status: AccountingPeriodStatus
    state: str
    required_task_count: int
    completed_required_count: int
    completion_ratio: Decimal
    blocker_count: int
    warning_count: int
    blockers: list[ReadinessBlockerSchema]
    warnings: list[ReadinessBlockerSchema]
    blockers_by_category: dict[str, list[ReadinessBlockerSchema]]
    evidence_freshness: str
    version: int

    @classmethod
    def from_domain(cls, readiness: CloseReadiness) -> ReadinessResponse:
        blockers = [ReadinessBlockerSchema.model_validate(item, from_attributes=True) for item in readiness.blockers]
        warnings = [ReadinessBlockerSchema.model_validate(item, from_attributes=True) for item in readiness.warnings]
        grouped: dict[str, list[ReadinessBlockerSchema]] = {}
        for blocker in blockers:
            grouped.setdefault(blocker.category, []).append(blocker)
        return cls(
            cycle_id=readiness.cycle_id,
            cycle_status=readiness.cycle_status,
            period_status=readiness.period_status,
            state=readiness.state,
            required_task_count=readiness.required_task_count,
            completed_required_count=readiness.completed_required_count,
            completion_ratio=readiness.completion_ratio,
            blocker_count=readiness.blocker_count,
            warning_count=readiness.warning_count,
            blockers=blockers,
            warnings=warnings,
            blockers_by_category=grouped,
            evidence_freshness=readiness.evidence_freshness,
            version=readiness.version,
        )


class ChecklistTaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=MAX_CHECKLIST_TITLE_LENGTH)
    description: str = Field(default="", max_length=MAX_CHECKLIST_DESCRIPTION_LENGTH)
    category: str = Field(default="custom", min_length=1, max_length=80)
    required: bool = False
    owner_user_id: int | None = Field(default=None, ge=1)
    due_date: date | None = None
    notes: str | None = Field(default=None, max_length=MAX_CHECKLIST_NOTES_LENGTH)


class ChecklistTaskUpdate(BaseModel):
    version: int = Field(ge=1)
    complete: bool
    notes: str | None = Field(default=None, max_length=MAX_CHECKLIST_NOTES_LENGTH)
    owner_user_id: int | None = Field(default=None, ge=1)
    due_date: date | None = None


class ChecklistTaskRead(OrmSchema):
    id: int
    cycle_id: int
    task_key: str
    title: str
    description: str
    category: str
    required: bool
    control_type: CloseTaskControlType
    status: CloseTaskStatus
    owner_user_id: int | None
    due_date: date | None
    completed_by_id: int | None
    completed_at: datetime | None
    notes: str | None
    evidence_metadata: dict[str, Any]
    sort_order: int
    version: int


class ReconciliationUpsert(BaseModel):
    account_id: int = Field(ge=1)
    control_balance: Decimal | None = None
    tolerance: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str | None = Field(default=None, max_length=MAX_RECONCILIATION_NOTES_LENGTH)
    evidence_metadata: dict[str, Any] = Field(default_factory=dict)
    owner_user_id: int | None = Field(default=None, ge=1)
    version: int | None = Field(default=None, ge=1)

    @field_validator("evidence_metadata")
    @classmethod
    def bounded_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], validate_metadata(value))


class ReconciliationApprove(BaseModel):
    version: int = Field(ge=1)


class ReconciliationRead(OrmSchema):
    id: int
    cycle_id: int
    account_id: int
    ledger_ending_balance: Decimal
    control_balance: Decimal | None
    difference: Decimal | None
    tolerance: Decimal
    status: ReconciliationStatus
    owner_user_id: int | None
    prepared_by_id: int | None
    reviewer_user_id: int | None
    approved_by_id: int | None
    notes: str | None
    evidence_metadata: dict[str, Any]
    prepared_at: datetime | None
    reviewed_at: datetime | None
    approved_at: datetime | None
    version: int


class VarianceMaterializeRequest(BaseModel):
    budget_id: int = Field(ge=1)
    horizon: int = Field(default=30, ge=1, le=365)
    absolute_threshold: Decimal = Field(default=Decimal("1000"), ge=0)
    percentage_threshold: Decimal | None = Field(default=Decimal("0.10"), ge=0)
    refresh: bool = True


class VarianceUpdate(BaseModel):
    version: int = Field(ge=1)
    disposition: VarianceDisposition
    note: str | None = Field(default=None, max_length=MAX_RECONCILIATION_NOTES_LENGTH)
    owner_user_id: int | None = Field(default=None, ge=1)


class VarianceRead(OrmSchema):
    id: int
    cycle_id: int
    budget_id: int
    account_id: int
    period_start: date
    horizon: int
    budget_amount: Decimal
    actual_amount: Decimal
    variance_amount: Decimal
    variance_percent: Decimal | None
    absolute_threshold: Decimal
    percentage_threshold: Decimal | None
    is_material: bool
    disposition: VarianceDisposition
    owner_user_id: int | None
    reviewer_user_id: int | None
    note: str | None
    reviewed_at: datetime | None
    report_metadata: dict[str, Any]
    version: int


class JournalApprovalRequest(BaseModel):
    transaction_id: int | None = Field(default=None, ge=1)
    staged_transaction_id: int | None = Field(default=None, ge=1)
    reason: str | None = Field(default=None, max_length=MAX_APPROVAL_COMMENT_LENGTH)

    @model_validator(mode="after")
    def one_reference(self) -> JournalApprovalRequest:
        if (self.transaction_id is None) == (self.staged_transaction_id is None):
            raise ValueError("exactly one transaction reference is required")
        return self


class JournalDecisionRequest(BaseModel):
    version: int = Field(ge=1)
    decision: JournalApprovalStatus
    reason: str | None = Field(default=None, max_length=MAX_APPROVAL_COMMENT_LENGTH)

    @field_validator("decision")
    @classmethod
    def allowed_decision(cls, value: JournalApprovalStatus) -> JournalApprovalStatus:
        if value == JournalApprovalStatus.REQUESTED:
            raise ValueError("REQUESTED is not a decision")
        return value


class JournalDecisionRead(OrmSchema):
    id: int
    approval_id: int
    from_status: JournalApprovalStatus
    to_status: JournalApprovalStatus
    decided_by_id: int
    decided_at: datetime
    reason: str | None


class JournalApprovalRead(OrmSchema):
    id: int
    cycle_id: int
    transaction_id: int | None
    staged_transaction_id: int | None
    requestor_user_id: int
    status: JournalApprovalStatus
    requested_at: datetime
    decided_by_id: int | None
    decided_at: datetime | None
    reason: str | None
    version: int
    history: list[JournalDecisionRead] = Field(default_factory=list)


class EvidenceFileRead(BaseModel):
    name: str
    byte_length: int
    sha256: str


class EvidenceGenerateResponse(BaseModel):
    cycle_id: int
    manifest_sha256: str
    source_version: int
    archive_bytes: int
    filename: str
    files: list[EvidenceFileRead]

    @classmethod
    def from_bundle(cls, cycle_id: int, bundle: EvidenceBundle) -> EvidenceGenerateResponse:
        return cls(
            cycle_id=cycle_id,
            manifest_sha256=bundle.manifest_sha256,
            source_version=bundle.source_version,
            archive_bytes=len(bundle.content),
            filename=bundle.filename,
            files=[EvidenceFileRead.model_validate(item, from_attributes=True) for item in bundle.files],
        )


class EvidencePreviewResponse(BaseModel):
    cycle_id: int
    source_version: int
    deterministic_files: list[str]
    latest_manifest_sha256: str | None
    freshness: str
    maximum_archive_bytes: int
    maximum_rows: int
