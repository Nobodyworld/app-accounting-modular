"""Ledger management routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..db import get_session
from ..models.models import Account, Transaction, User
from ..schemas import AccountCreate, TransactionCreate, TrialBalanceResponse
from ..security import get_current_organization, get_current_user
from ..services.ledger_service import LedgerService

router = APIRouter(prefix="/ledger", tags=["ledger"])


def _service_for_org(session: Session, organization_id: int) -> LedgerService:
    # TODO - Reuse a per-request service cache to avoid redundant instantiations.
    return LedgerService(session, organization_id=organization_id)


@router.post("/account", response_model=Account)
def create_account(
    payload: AccountCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Account:
    """Create a new ledger account."""

    org_ctx = get_current_organization(
        organization_id=payload.organization_id,
        session=session,
        current_user=current_user,
    )
    if not (org_ctx.membership.is_admin or org_ctx.membership.can_manage_ledger):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    service = _service_for_org(session, org_ctx.organization.id)
    data = payload.model_dump(exclude={"organization_id"})
    # TODO - Validate account code uniqueness before delegating to the service layer.
    return service.create_account(**data)


@router.post("/post", response_model=Transaction)
def post_transaction(
    payload: TransactionCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Transaction:
    """Persist a balanced journal transaction."""

    org_ctx = get_current_organization(
        organization_id=payload.organization_id,
        session=session,
        current_user=current_user,
    )
    if not (org_ctx.membership.is_admin or org_ctx.membership.can_manage_ledger):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    service = _service_for_org(session, org_ctx.organization.id)
    # TODO - Capture posting source metadata for reconciliation dashboards.
    return service.post_transaction(
        payload.date,
        payload.description,
        list(payload.ledger_payload()),
    )


@router.get("/trial-balance", response_model=TrialBalanceResponse)
def trial_balance(
    organization_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> TrialBalanceResponse:
    """Return the current trial balance across all accounts."""

    org_ctx = get_current_organization(
        organization_id=organization_id,
        session=session,
        current_user=current_user,
    )
    if not (
        org_ctx.membership.is_admin
        or org_ctx.membership.can_manage_ledger
        or org_ctx.membership.can_manage_tax
    ):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    service = _service_for_org(session, org_ctx.organization.id)
    # TODO - Support comparative periods and currency filters in trial balance responses.
    return TrialBalanceResponse.from_service(service.trial_balance())


__all__ = ["router"]
