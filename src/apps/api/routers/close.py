"""Authenticated accountant close and reconciliation API."""

from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlmodel import Session

from ..close_schemas import (
    ChecklistTaskCreate,
    ChecklistTaskRead,
    ChecklistTaskUpdate,
    CycleCreate,
    CycleRead,
    EvidenceGenerateResponse,
    EvidencePreviewResponse,
    JournalApprovalRead,
    JournalApprovalRequest,
    JournalDecisionRead,
    JournalDecisionRequest,
    PeriodCreate,
    PeriodRead,
    ReadinessResponse,
    ReasonedTransitionRequest,
    ReconciliationApprove,
    ReconciliationRead,
    ReconciliationUpsert,
    VarianceMaterializeRequest,
    VarianceRead,
    VarianceUpdate,
    VersionRequest,
)
from ..db import get_session
from ..limits import MAX_CLOSE_LIST_PAGE
from ..models.models import CloseCycleStatus, CloseTaskStatus, Membership, User
from ..security import get_current_organization, get_current_user
from ..services.close_evidence_service import CloseEvidenceService
from ..services.close_service import (
    CloseConflictError,
    CloseDomainError,
    CloseNotFoundError,
    CloseService,
    CloseValidationError,
)
from ..services.reconciliation_service import ReconciliationService

router = APIRouter(prefix="/close", tags=["close"])


def _actor_id(current_user: User) -> int:
    if current_user.id is None:
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    return current_user.id


def _context(
    organization_id: int,
    session: Session,
    current_user: User,
    *,
    manager: bool = False,
    admin: bool = False,
) -> tuple[int, int, Membership]:
    context = get_current_organization(organization_id, session, current_user)
    membership = context.membership
    if admin and not membership.is_admin:
        raise HTTPException(status_code=403, detail="Organization administrator access is required")
    if manager and not (membership.is_admin or membership.can_manage_ledger):
        raise HTTPException(status_code=403, detail="Ledger manager access is required")
    if context.organization.id is None:
        raise HTTPException(status_code=500, detail="Organization identifier is missing")
    return context.organization.id, _actor_id(current_user), membership


def _service(
    organization_id: int,
    session: Session,
    current_user: User,
    *,
    manager: bool = False,
    admin: bool = False,
) -> tuple[CloseService, Membership]:
    org_id, actor_id, membership = _context(organization_id, session, current_user, manager=manager, admin=admin)
    return CloseService(session, org_id, actor_id), membership


def _reconciliation_service(
    organization_id: int,
    session: Session,
    current_user: User,
    *,
    manager: bool = False,
    admin: bool = False,
) -> tuple[ReconciliationService, Membership]:
    org_id, actor_id, membership = _context(organization_id, session, current_user, manager=manager, admin=admin)
    return ReconciliationService(session, org_id, actor_id), membership


def _raise_domain(exc: CloseDomainError) -> NoReturn:
    if isinstance(exc, CloseNotFoundError):
        code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, CloseConflictError):
        code = status.HTTP_409_CONFLICT
    elif isinstance(exc, CloseValidationError):
        code = status.HTTP_400_BAD_REQUEST
    else:
        code = status.HTTP_400_BAD_REQUEST
    raise HTTPException(status_code=code, detail={"code": exc.code, "message": str(exc)}) from exc


@router.post("/periods", response_model=PeriodRead, status_code=201)
def create_period(
    payload: PeriodCreate,
    organization_id: int = Query(ge=1),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> PeriodRead:
    service, _ = _service(organization_id, session, current_user, manager=True)
    try:
        return PeriodRead.model_validate(service.create_period(payload.label, payload.start_date, payload.end_date))
    except CloseDomainError as exc:
        _raise_domain(exc)


@router.get("/periods", response_model=list[PeriodRead])
def list_periods(
    organization_id: int = Query(ge=1),
    limit: int = Query(default=100, ge=1, le=MAX_CLOSE_LIST_PAGE),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[PeriodRead]:
    service, _ = _service(organization_id, session, current_user)
    return [PeriodRead.model_validate(item) for item in service.list_periods(limit=limit, offset=offset)]


@router.get("/periods/{period_id}", response_model=PeriodRead)
def get_period(
    period_id: int,
    organization_id: int = Query(ge=1),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> PeriodRead:
    service, _ = _service(organization_id, session, current_user)
    try:
        return PeriodRead.model_validate(service.require_period(period_id))
    except CloseDomainError as exc:
        _raise_domain(exc)


@router.post("/periods/{period_id}/cycles", response_model=CycleRead, status_code=201)
def create_cycle(
    period_id: int,
    payload: CycleCreate,
    organization_id: int = Query(ge=1),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CycleRead:
    service, _ = _service(organization_id, session, current_user, manager=True)
    try:
        cycle = service.create_cycle(period_id, **payload.model_dump())
        return CycleRead.model_validate(cycle)
    except CloseDomainError as exc:
        _raise_domain(exc)


@router.get("/periods/{period_id}/cycles", response_model=list[CycleRead])
def list_cycles(
    period_id: int,
    organization_id: int = Query(ge=1),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[CycleRead]:
    service, _ = _service(organization_id, session, current_user)
    try:
        return [CycleRead.model_validate(item) for item in service.list_cycles(period_id)]
    except CloseDomainError as exc:
        _raise_domain(exc)


@router.get("/cycles/{cycle_id}", response_model=CycleRead)
def get_cycle(
    cycle_id: int,
    organization_id: int = Query(ge=1),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CycleRead:
    service, _ = _service(organization_id, session, current_user)
    try:
        return CycleRead.model_validate(service.require_cycle(cycle_id))
    except CloseDomainError as exc:
        _raise_domain(exc)


def _transition(
    action: str,
    cycle_id: int,
    payload: VersionRequest | ReasonedTransitionRequest,
    organization_id: int,
    session: Session,
    current_user: User,
) -> CycleRead:
    admin = action in {"close", "reopen", "cancel"}
    service, _ = _service(organization_id, session, current_user, manager=not admin, admin=admin)
    try:
        if action == "start":
            cycle = service.start(cycle_id, payload.version)
        elif action == "ready":
            cycle = service.mark_ready(cycle_id, payload.version)
        elif action == "close":
            cycle = service.close(cycle_id, payload.version)
        elif action == "reopen" and isinstance(payload, ReasonedTransitionRequest):
            cycle = service.reopen(cycle_id, payload.version, payload.reason)
        elif action == "cancel" and isinstance(payload, ReasonedTransitionRequest):
            cycle = service.cancel(cycle_id, payload.version, payload.reason)
        else:  # pragma: no cover - fixed route dispatch
            raise CloseValidationError("Invalid close transition")
        return CycleRead.model_validate(cycle)
    except CloseDomainError as exc:
        _raise_domain(exc)


@router.post("/cycles/{cycle_id}/start", response_model=CycleRead)
def start_cycle(
    cycle_id: int,
    payload: VersionRequest,
    organization_id: int = Query(ge=1),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CycleRead:
    return _transition("start", cycle_id, payload, organization_id, session, current_user)


@router.post("/cycles/{cycle_id}/ready", response_model=CycleRead)
def mark_cycle_ready(
    cycle_id: int,
    payload: VersionRequest,
    organization_id: int = Query(ge=1),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CycleRead:
    return _transition("ready", cycle_id, payload, organization_id, session, current_user)


@router.post("/cycles/{cycle_id}/close", response_model=CycleRead)
def close_cycle(
    cycle_id: int,
    payload: VersionRequest,
    organization_id: int = Query(ge=1),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CycleRead:
    return _transition("close", cycle_id, payload, organization_id, session, current_user)


@router.post("/cycles/{cycle_id}/reopen", response_model=CycleRead)
def reopen_cycle(
    cycle_id: int,
    payload: ReasonedTransitionRequest,
    organization_id: int = Query(ge=1),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CycleRead:
    return _transition("reopen", cycle_id, payload, organization_id, session, current_user)


@router.post("/cycles/{cycle_id}/cancel", response_model=CycleRead)
def cancel_cycle(
    cycle_id: int,
    payload: ReasonedTransitionRequest,
    organization_id: int = Query(ge=1),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> CycleRead:
    return _transition("cancel", cycle_id, payload, organization_id, session, current_user)


@router.get("/cycles/{cycle_id}/readiness", response_model=ReadinessResponse)
def get_readiness(
    cycle_id: int,
    organization_id: int = Query(ge=1),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ReadinessResponse:
    service, _ = _service(organization_id, session, current_user)
    try:
        return ReadinessResponse.from_domain(service.readiness(cycle_id))
    except CloseDomainError as exc:
        _raise_domain(exc)


@router.get("/cycles/{cycle_id}/checklist", response_model=list[ChecklistTaskRead])
def list_checklist(
    cycle_id: int,
    organization_id: int = Query(ge=1),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[ChecklistTaskRead]:
    service, _ = _service(organization_id, session, current_user)
    try:
        readiness = service.readiness(cycle_id)
        blockers = {item.code for item in readiness.blockers}
        blocker_by_key = {
            "staged_journal_exceptions_resolved": "STAGED_ITEMS_UNRESOLVED",
            "trial_balance_balanced": "TRIAL_BALANCE_UNBALANCED",
            "required_reconciliations_complete": "RECONCILIATIONS_INCOMPLETE",
            "material_variances_reviewed": "MATERIAL_VARIANCES_UNRESOLVED",
            "required_journal_approvals_complete": "JOURNAL_APPROVALS_INCOMPLETE",
            "close_evidence_generated": "CLOSE_EVIDENCE_NOT_CURRENT",
        }
        output: list[ChecklistTaskRead] = []
        for task in service.list_checklist(cycle_id):
            payload = ChecklistTaskRead.model_validate(task).model_dump()
            blocker = blocker_by_key.get(task.task_key)
            if blocker is not None:
                if task.task_key == "required_reconciliations_complete" and "RECONCILIATIONS_MISSING" in blockers:
                    payload["status"] = CloseTaskStatus.PENDING
                else:
                    payload["status"] = CloseTaskStatus.PENDING if blocker in blockers else CloseTaskStatus.COMPLETE
            if task.task_key == "final_close_approved":
                payload["status"] = (
                    CloseTaskStatus.COMPLETE
                    if readiness.cycle_status in {CloseCycleStatus.READY_FOR_APPROVAL, CloseCycleStatus.CLOSED}
                    else CloseTaskStatus.PENDING
                )
            output.append(ChecklistTaskRead.model_validate(payload))
        return output
    except CloseDomainError as exc:
        _raise_domain(exc)


@router.post("/cycles/{cycle_id}/checklist", response_model=ChecklistTaskRead, status_code=201)
def create_checklist_task(
    cycle_id: int,
    payload: ChecklistTaskCreate,
    organization_id: int = Query(ge=1),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ChecklistTaskRead:
    service, _ = _service(organization_id, session, current_user, manager=True)
    try:
        return ChecklistTaskRead.model_validate(service.create_custom_task(cycle_id, **payload.model_dump()))
    except CloseDomainError as exc:
        _raise_domain(exc)


@router.patch("/cycles/{cycle_id}/checklist/{task_id}", response_model=ChecklistTaskRead)
def update_checklist_task(
    cycle_id: int,
    task_id: int,
    payload: ChecklistTaskUpdate,
    organization_id: int = Query(ge=1),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ChecklistTaskRead:
    service, membership = _service(organization_id, session, current_user, manager=True)
    try:
        return ChecklistTaskRead.model_validate(
            service.update_manual_task(cycle_id, task_id, is_admin=membership.is_admin, **payload.model_dump())
        )
    except CloseDomainError as exc:
        _raise_domain(exc)


@router.get("/cycles/{cycle_id}/reconciliations", response_model=list[ReconciliationRead])
def list_reconciliations(
    cycle_id: int,
    organization_id: int = Query(ge=1),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[ReconciliationRead]:
    service, _ = _reconciliation_service(organization_id, session, current_user)
    try:
        return [ReconciliationRead.model_validate(item) for item in service.list_reconciliations(cycle_id)]
    except CloseDomainError as exc:
        _raise_domain(exc)


@router.post("/cycles/{cycle_id}/reconciliations", response_model=ReconciliationRead, status_code=201)
@router.patch("/cycles/{cycle_id}/reconciliations/{reconciliation_id}", response_model=ReconciliationRead)
def upsert_reconciliation(
    cycle_id: int,
    payload: ReconciliationUpsert,
    organization_id: int = Query(ge=1),
    reconciliation_id: int | None = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ReconciliationRead:
    service, _ = _reconciliation_service(organization_id, session, current_user, manager=True)
    try:
        item = service.prepare_reconciliation(cycle_id, **payload.model_dump())
        if reconciliation_id is not None and item.id != reconciliation_id:
            raise CloseNotFoundError("Reconciliation not found")
        return ReconciliationRead.model_validate(item)
    except CloseDomainError as exc:
        _raise_domain(exc)


@router.post("/cycles/{cycle_id}/reconciliations/{reconciliation_id}/approve", response_model=ReconciliationRead)
def approve_reconciliation(
    cycle_id: int,
    reconciliation_id: int,
    payload: ReconciliationApprove,
    organization_id: int = Query(ge=1),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> ReconciliationRead:
    service, _ = _reconciliation_service(organization_id, session, current_user, manager=True)
    try:
        return ReconciliationRead.model_validate(
            service.approve_reconciliation(cycle_id, reconciliation_id, version=payload.version)
        )
    except CloseDomainError as exc:
        _raise_domain(exc)


@router.post("/cycles/{cycle_id}/variance-reviews/from-budget", response_model=list[VarianceRead])
def materialize_variances(
    cycle_id: int,
    payload: VarianceMaterializeRequest,
    organization_id: int = Query(ge=1),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[VarianceRead]:
    service, _ = _reconciliation_service(organization_id, session, current_user, manager=True)
    try:
        return [
            VarianceRead.model_validate(item)
            for item in service.materialize_variances(cycle_id, **payload.model_dump())
        ]
    except CloseDomainError as exc:
        _raise_domain(exc)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "BUDGET_REPORT_ERROR", "message": str(exc)}) from exc


@router.get("/cycles/{cycle_id}/variance-reviews", response_model=list[VarianceRead])
def list_variances(
    cycle_id: int,
    organization_id: int = Query(ge=1),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[VarianceRead]:
    service, _ = _reconciliation_service(organization_id, session, current_user)
    try:
        return [VarianceRead.model_validate(item) for item in service.list_variances(cycle_id)]
    except CloseDomainError as exc:
        _raise_domain(exc)


@router.patch("/cycles/{cycle_id}/variance-reviews/{review_id}", response_model=VarianceRead)
def update_variance(
    cycle_id: int,
    review_id: int,
    payload: VarianceUpdate,
    organization_id: int = Query(ge=1),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> VarianceRead:
    service, _ = _reconciliation_service(organization_id, session, current_user, manager=True)
    try:
        return VarianceRead.model_validate(service.update_variance(cycle_id, review_id, **payload.model_dump()))
    except CloseDomainError as exc:
        _raise_domain(exc)


def _approval_response(service: ReconciliationService, item: object) -> JournalApprovalRead:
    payload = JournalApprovalRead.model_validate(item).model_dump()
    approval_id = int(payload["id"])
    payload["history"] = [
        JournalDecisionRead.model_validate(decision).model_dump() for decision in service.approval_history(approval_id)
    ]
    return JournalApprovalRead.model_validate(payload)


@router.post("/cycles/{cycle_id}/journal-approvals", response_model=JournalApprovalRead, status_code=201)
def request_journal_approval(
    cycle_id: int,
    payload: JournalApprovalRequest,
    organization_id: int = Query(ge=1),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> JournalApprovalRead:
    service, _ = _reconciliation_service(organization_id, session, current_user, manager=True)
    try:
        return _approval_response(service, service.request_approval(cycle_id, **payload.model_dump()))
    except CloseDomainError as exc:
        _raise_domain(exc)


@router.get("/cycles/{cycle_id}/journal-approvals", response_model=list[JournalApprovalRead])
def list_journal_approvals(
    cycle_id: int,
    organization_id: int = Query(ge=1),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[JournalApprovalRead]:
    service, _ = _reconciliation_service(organization_id, session, current_user)
    try:
        return [_approval_response(service, item) for item in service.list_approvals(cycle_id)]
    except CloseDomainError as exc:
        _raise_domain(exc)


@router.post("/cycles/{cycle_id}/journal-approvals/{approval_id}/decide", response_model=JournalApprovalRead)
def decide_journal_approval(
    cycle_id: int,
    approval_id: int,
    payload: JournalDecisionRequest,
    organization_id: int = Query(ge=1),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> JournalApprovalRead:
    service, membership = _reconciliation_service(organization_id, session, current_user, manager=True)
    try:
        item = service.decide_approval(cycle_id, approval_id, is_admin=membership.is_admin, **payload.model_dump())
        return _approval_response(service, item)
    except CloseDomainError as exc:
        _raise_domain(exc)


@router.get("/cycles/{cycle_id}/evidence/preview", response_model=EvidencePreviewResponse)
def evidence_preview(
    cycle_id: int,
    organization_id: int = Query(ge=1),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> EvidencePreviewResponse:
    org_id, actor_id, _ = _context(organization_id, session, current_user)
    try:
        return EvidencePreviewResponse.model_validate(CloseEvidenceService(session, org_id, actor_id).preview(cycle_id))
    except CloseDomainError as exc:
        _raise_domain(exc)


@router.post("/cycles/{cycle_id}/evidence", response_model=EvidenceGenerateResponse)
def generate_evidence(
    cycle_id: int,
    organization_id: int = Query(ge=1),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> EvidenceGenerateResponse:
    org_id, actor_id, _ = _context(organization_id, session, current_user, manager=True)
    service = CloseEvidenceService(session, org_id, actor_id)
    try:
        bundle = service.build_bundle(cycle_id)
        service.record_generation(cycle_id, bundle)
        bundle = service.build_bundle(cycle_id)
        return EvidenceGenerateResponse.from_bundle(cycle_id, bundle)
    except CloseDomainError as exc:
        _raise_domain(exc)


@router.get("/cycles/{cycle_id}/evidence/download")
def download_evidence(
    cycle_id: int,
    organization_id: int = Query(ge=1),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    org_id, actor_id, _ = _context(organization_id, session, current_user, manager=True)
    try:
        bundle = CloseEvidenceService(session, org_id, actor_id).build_bundle(cycle_id)
    except CloseDomainError as exc:
        _raise_domain(exc)
    return Response(
        content=bundle.content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{bundle.filename}"',
            "X-Manifest-SHA256": bundle.manifest_sha256,
        },
    )


__all__ = ["router"]
