"""Workflow orchestration API endpoints."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from ..db import get_session
from ..models.models import Account, StagedPosting, StagedTransaction, Transaction, User
from ..schemas import (
    StagedPostingIngest,
    StagedPostingRead,
    StagedTransactionRead,
    WorkflowIngestRequest,
    WorkflowIngestResponse,
    WorkflowProcessRequest,
    WorkflowResultSchema,
)
from ..security import get_current_organization, get_current_user
from ..services.workflow_service import WorkflowService

router = APIRouter(prefix="/workflow", tags=["workflow"])
_ORGANIZATION_METADATA_KEY = "_organization_id"
_ORIGINAL_SOURCE_METADATA_KEY = "_workflow_source"


def _require_id(value: int | None, *, label: str) -> int:
    if value is None:
        raise HTTPException(status_code=500, detail=f"{label} missing identifier")
    return value


def _require_workflow_access(
    organization_id: int,
    *,
    session: Session,
    current_user: User,
) -> int:
    org_ctx = get_current_organization(
        organization_id=organization_id,
        session=session,
        current_user=current_user,
    )
    if not (org_ctx.membership.is_admin or org_ctx.membership.can_manage_ledger):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return _require_id(org_ctx.organization.id, label="organization")


def _storage_source(source: str, organization_id: int) -> str:
    """Namespace idempotency keys while preserving the caller-visible source."""

    return f"{source}::organization:{organization_id}"


def _posting_payload(
    posting: StagedPostingRead | StagedPostingIngest,
    *,
    session: Session,
    organization_id: int,
) -> dict[str, object]:
    account_id = posting.account_id
    if account_id is not None:
        account = session.get(Account, account_id)
        if account is not None and account.organization_id != organization_id:
            raise HTTPException(status_code=404, detail="Account not found")
    else:
        stmt = select(Account).where(Account.organization_id == organization_id)
        if posting.account_code:
            stmt = stmt.where(Account.code == posting.account_code)
        elif posting.account_name:
            stmt = stmt.where(Account.name == posting.account_name)
        matches = list(session.exec(stmt))
        if not matches:
            raise HTTPException(status_code=404, detail="Account not found")
        if len(matches) > 1:
            raise HTTPException(
                status_code=400, detail="Account reference is ambiguous"
            )
        account_id = matches[0].id

    return {
        "account_id": account_id,
        "account_code": posting.account_code,
        "account_name": posting.account_name,
        "debit": float(posting.debit),
        "credit": float(posting.credit),
        "currency": posting.currency,
        "metadata": getattr(posting, "metadata", {}),
    }


def _record_organization_ids(
    session: Session,
    staged: StagedTransaction,
    postings: list[StagedPosting],
) -> set[int]:
    organization_ids: set[int] = set()
    if staged.transaction_id is not None:
        transaction = session.get(Transaction, staged.transaction_id)
        if transaction is not None and transaction.organization_id is not None:
            organization_ids.add(transaction.organization_id)

    for posting in postings:
        if posting.account_id is not None:
            account = session.get(Account, posting.account_id)
            if account is not None and account.organization_id is not None:
                organization_ids.add(account.organization_id)
            continue

        stmt = select(Account)
        if posting.account_code:
            stmt = stmt.where(Account.code == posting.account_code)
        elif posting.account_name:
            stmt = stmt.where(Account.name == posting.account_name)
        else:
            continue
        for account in session.exec(stmt):
            if account.organization_id is not None:
                organization_ids.add(account.organization_id)

    return organization_ids


def _record_belongs_to_organization(
    session: Session,
    staged: StagedTransaction,
    postings: list[StagedPosting],
    organization_id: int,
) -> bool:
    marker = staged.source_metadata.get(_ORGANIZATION_METADATA_KEY)
    if marker is not None and marker != organization_id:
        return False
    return _record_organization_ids(session, staged, postings) == {organization_id}


def _require_scoped_record(
    service: WorkflowService,
    session: Session,
    staged_id: int,
    organization_id: int,
) -> tuple[StagedTransaction, list[StagedPosting]]:
    record = service.get_transaction(staged_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Staged transaction not found")
    staged, postings = record
    if not _record_belongs_to_organization(session, staged, postings, organization_id):
        raise HTTPException(status_code=404, detail="Staged transaction not found")
    return staged, postings


def _scoped_records(
    service: WorkflowService,
    session: Session,
    organization_id: int,
    *,
    limit: int,
    offset: int,
) -> list[tuple[StagedTransaction, list[StagedPosting]]]:
    scoped: list[tuple[StagedTransaction, list[StagedPosting]]] = []
    cursor = 0
    page_size = 500
    while True:
        page = service.list_transactions(limit=page_size, offset=cursor)
        if not page:
            break
        scoped.extend(
            (staged, postings)
            for staged, postings in page
            if _record_belongs_to_organization(
                session, staged, postings, organization_id
            )
        )
        cursor += len(page)
        if len(page) < page_size:
            break
    return scoped[offset : offset + limit]


def _serialize_staged(
    staged: StagedTransaction,
    postings: list[StagedPosting],
) -> StagedTransactionRead:
    staged_id = _require_id(staged.id, label="staged transaction")
    posting_models = [
        StagedPostingRead(
            id=_require_id(post.id, label="staged posting"),
            account_id=post.account_id,
            account_code=post.account_code,
            account_name=post.account_name,
            debit=Decimal(str(post.debit)),
            credit=Decimal(str(post.credit)),
            currency=post.currency,
            metadata=post.context,
        )
        for post in postings
    ]
    source_metadata = {
        key: value
        for key, value in staged.source_metadata.items()
        if key not in {_ORGANIZATION_METADATA_KEY, _ORIGINAL_SOURCE_METADATA_KEY}
    }
    return StagedTransactionRead(
        id=staged_id,
        date=staged.date,
        description=staged.description,
        status=staged.status,
        source=str(
            staged.source_metadata.get(_ORIGINAL_SOURCE_METADATA_KEY, staged.source)
        ),
        source_reference=staged.source_reference,
        source_metadata=source_metadata,
        validation_errors=staged.validation_errors,
        transaction_id=staged.transaction_id,
        ingested_at=staged.ingested_at,
        updated_at=staged.updated_at,
        postings=posting_models,
    )


@router.post("/ingest", response_model=WorkflowIngestResponse)
def ingest_transactions(
    payload: WorkflowIngestRequest,
    organization_id: int = Query(gt=0),
    s: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> WorkflowIngestResponse:
    """Persist raw transactions to the staging tables and optionally process them."""

    org_id = _require_workflow_access(
        organization_id, session=s, current_user=current_user
    )
    svc = WorkflowService(s)
    internal_metadata = {
        _ORGANIZATION_METADATA_KEY: org_id,
        _ORIGINAL_SOURCE_METADATA_KEY: payload.source,
    }
    try:
        staged = svc.ingest_transactions(
            (
                {
                    "date": txn.date,
                    "description": txn.description,
                    "postings": [
                        _posting_payload(posting, session=s, organization_id=org_id)
                        for posting in txn.postings
                    ],
                    "source_reference": txn.source_reference,
                    "metadata": {**txn.metadata, **internal_metadata},
                }
                for txn in payload.transactions
            ),
            source=_storage_source(payload.source, org_id),
            source_reference=payload.source_reference,
            metadata={**payload.metadata, **internal_metadata},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    results = []
    if payload.auto_process:
        staged_ids = [
            _require_id(item.id, label="staged transaction") for item in staged
        ]
        results = svc.process_transactions(staged_ids)

    return WorkflowIngestResponse(
        staged_ids=[
            _require_id(item.id, label="staged transaction") for item in staged
        ],
        results=[WorkflowResultSchema.from_result(result) for result in results],
    )


@router.post("/process", response_model=list[WorkflowResultSchema])
def process_transactions(
    payload: WorkflowProcessRequest,
    organization_id: int = Query(gt=0),
    s: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> list[WorkflowResultSchema]:
    """Trigger validation/posting for staged transactions."""

    org_id = _require_workflow_access(
        organization_id, session=s, current_user=current_user
    )
    svc = WorkflowService(s)
    if payload.staged_ids is None:
        staged_ids = [
            _require_id(staged.id, label="staged transaction")
            for staged, _ in _scoped_records(svc, s, org_id, limit=500, offset=0)
        ]
    else:
        staged_ids = list(dict.fromkeys(payload.staged_ids))
        for staged_id in staged_ids:
            _require_scoped_record(svc, s, staged_id, org_id)
    if not staged_ids:
        return []

    results = svc.process_transactions(staged_ids, auto_post=payload.auto_post)
    return [WorkflowResultSchema.from_result(result) for result in results]


@router.get("/{staged_id}", response_model=StagedTransactionRead)
def get_staged_transaction(
    staged_id: int,
    organization_id: int = Query(gt=0),
    s: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> StagedTransactionRead:
    """Return a staged transaction including its postings."""

    org_id = _require_workflow_access(
        organization_id, session=s, current_user=current_user
    )
    svc = WorkflowService(s)
    staged, postings = _require_scoped_record(svc, s, staged_id, org_id)
    return _serialize_staged(staged, postings)


@router.get("", response_model=list[StagedTransactionRead])
@router.get("/", response_model=list[StagedTransactionRead], include_in_schema=False)
def list_staged_transactions(
    organization_id: int = Query(gt=0),
    s: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[StagedTransactionRead]:
    """List staged transactions ordered by creation time."""

    org_id = _require_workflow_access(
        organization_id, session=s, current_user=current_user
    )
    svc = WorkflowService(s)
    return [
        _serialize_staged(staged, postings)
        for staged, postings in _scoped_records(
            svc, s, org_id, limit=limit, offset=offset
        )
    ]
