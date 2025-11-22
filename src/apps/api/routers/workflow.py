"""Workflow orchestration API endpoints."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from ..db import get_session
from ..schemas import (
    StagedPostingIngest,
    StagedPostingRead,
    StagedTransactionRead,
    WorkflowIngestRequest,
    WorkflowIngestResponse,
    WorkflowProcessRequest,
    WorkflowResultSchema,
)
from ..services.workflow_service import WorkflowService

router = APIRouter(prefix="/workflow", tags=["workflow"])


def _require_id(value: int | None, *, label: str) -> int:
    if value is None:
        raise HTTPException(status_code=500, detail=f"{label} missing identifier")
    return value


def _posting_payload(posting: StagedPostingRead | StagedPostingIngest) -> dict[str, object]:
    return {
        "account_id": posting.account_id,
        "account_code": posting.account_code,
        "account_name": posting.account_name,
        "debit": float(posting.debit),
        "credit": float(posting.credit),
        "currency": posting.currency,
        "metadata": getattr(posting, "metadata", {}),
    }


@router.post("/ingest", response_model=WorkflowIngestResponse)
def ingest_transactions(payload: WorkflowIngestRequest, s: Session = Depends(get_session)) -> WorkflowIngestResponse:
    """Persist raw transactions to the staging tables and optionally process them."""

    svc = WorkflowService(s)
    staged = svc.ingest_transactions(
        (
            {
                "date": txn.date,
                "description": txn.description,
                "postings": [_posting_payload(posting) for posting in txn.postings],
                "source_reference": txn.source_reference,
                "metadata": txn.metadata,
            }
            for txn in payload.transactions
        ),
        source=payload.source,
        source_reference=payload.source_reference,
        metadata=payload.metadata,
    )

    results = []
    if payload.auto_process:
        staged_ids: list[int] = [_require_id(item.id, label="staged transaction") for item in staged]
        results = svc.process_transactions(staged_ids)

    return WorkflowIngestResponse(
        staged_ids=[_require_id(item.id, label="staged transaction") for item in staged],
        results=[WorkflowResultSchema.from_result(result) for result in results],
    )


@router.post("/process", response_model=list[WorkflowResultSchema])
def process_transactions(
    payload: WorkflowProcessRequest, s: Session = Depends(get_session)
) -> list[WorkflowResultSchema]:
    """Trigger validation/posting for staged transactions."""

    svc = WorkflowService(s)
    staged_ids = list(payload.staged_ids or [])
    results = svc.process_transactions(staged_ids, auto_post=payload.auto_post)
    return [WorkflowResultSchema.from_result(result) for result in results]


@router.get("/{staged_id}", response_model=StagedTransactionRead)
def get_staged_transaction(staged_id: int, s: Session = Depends(get_session)) -> StagedTransactionRead:
    """Return a staged transaction including its postings."""

    svc = WorkflowService(s)
    record = svc.get_transaction(staged_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Staged transaction not found")

    staged, postings = record
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
    return StagedTransactionRead(
        id=staged_id,
        date=staged.date,
        description=staged.description,
        status=staged.status,
        source=staged.source,
        source_reference=staged.source_reference,
        source_metadata=staged.source_metadata,
        validation_errors=staged.validation_errors,
        transaction_id=staged.transaction_id,
        ingested_at=staged.ingested_at,
        updated_at=staged.updated_at,
        postings=posting_models,
    )


@router.get("", response_model=list[StagedTransactionRead])
@router.get("/", response_model=list[StagedTransactionRead], include_in_schema=False)
def list_staged_transactions(
    s: Session = Depends(get_session),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[StagedTransactionRead]:
    """List staged transactions ordered by creation time."""

    svc = WorkflowService(s)
    items: list[StagedTransactionRead] = []
    for staged, postings in svc.list_transactions(limit=limit, offset=offset):
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
        items.append(
            StagedTransactionRead(
                id=staged_id,
                date=staged.date,
                description=staged.description,
                status=staged.status,
                source=staged.source,
                source_reference=staged.source_reference,
                source_metadata=staged.source_metadata,
                validation_errors=staged.validation_errors,
                transaction_id=staged.transaction_id,
                ingested_at=staged.ingested_at,
                updated_at=staged.updated_at,
                postings=posting_models,
            )
        )
    return items
