"""Foreign-exchange related routes."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlmodel import Session

from .. import db
from ..audit import AuditActor, get_current_actor, use_actor
from ..dependencies import session_with_audit_context
from ..models.models import User
from ..security import get_current_organization, get_current_user
from ..services.fx_service import FXService
from ..services.plugin_loader import load_provider

router = APIRouter(prefix="/fx", tags=["fx"])
_MAX_BACKFILL_DAYS = 31


def _sync_backfill_date(
    provider_key: str,
    organization_id: int,
    base: str,
    backfill_date: date,
    actor: AuditActor,
) -> None:
    """Run one backfill date with an isolated provider and database session."""

    handle = load_provider(provider_key)
    if "fx" not in handle.metadata.capabilities:
        raise ValueError(f"Provider '{provider_key}' does not support FX synchronization")

    with Session(db.engine, expire_on_commit=False) as session:
        service = FXService(
            session,
            handle.instance,
            organization_id=organization_id,
        )
        with use_actor(actor):
            service.sync(base=base, date_=backfill_date)


def _schedule_backfill(
    *,
    provider_key: str,
    organization_id: int,
    base: str,
    days: int,
    tasks: BackgroundTasks,
    actor: AuditActor,
) -> None:
    for offset in range(1, days + 1):
        backfill_date = date.today() - timedelta(days=offset)
        tasks.add_task(
            _sync_backfill_date,
            provider_key,
            organization_id,
            base,
            backfill_date,
            actor,
        )


def _trusted_background_actor(current_user: User, organization_id: int) -> AuditActor:
    current_actor = get_current_actor()
    return AuditActor(
        request_id=current_actor.request_id if current_actor is not None else str(uuid4()),
        user_id=current_user.id,
        organization_id=organization_id,
        source=current_actor.source if current_actor is not None else "api-background",
        user_label=current_user.email,
    )


@router.post("/sync", response_model=None)
def sync_fx(
    organization_id: Annotated[int, Query(ge=1)],
    background_tasks: BackgroundTasks,
    base: Annotated[str, Query(min_length=3, max_length=12, pattern=r"^[A-Za-z]+$")] = "USD",
    provider_key: Annotated[str, Query(min_length=1, max_length=128)] = "fx:ecb",
    backfill_days: Annotated[int, Query(ge=0, le=_MAX_BACKFILL_DAYS)] = 0,
    session: Session = Depends(session_with_audit_context),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    """Synchronise the latest FX rates from the configured provider."""

    org_ctx = get_current_organization(
        organization_id=organization_id,
        session=session,
        current_user=current_user,
    )
    membership = org_ctx.membership
    if not (membership.is_admin or membership.can_manage_fx):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    try:
        handle = load_provider(provider_key)
    except ValueError as exc:  # pragma: no cover - FastAPI integration
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if "fx" not in handle.metadata.capabilities:
        raise HTTPException(status_code=400, detail=f"Provider '{provider_key}' does not support FX synchronization")

    if org_ctx.organization.id is None:
        raise HTTPException(status_code=500, detail="Organization id is missing")
    org_id = org_ctx.organization.id
    normalized_base = base.strip().upper()
    service = FXService(
        session,
        handle.instance,
        organization_id=org_id,
    )
    count = service.sync(base=normalized_base)
    if backfill_days > 0:
        _schedule_backfill(
            provider_key=provider_key,
            organization_id=org_id,
            base=normalized_base,
            days=backfill_days,
            tasks=background_tasks,
            actor=_trusted_background_actor(current_user, org_id),
        )
    return {
        "synced": count,
        "provider": handle.metadata.name,
        "provider_key": handle.metadata.key,
        "base": normalized_base,
        "backfill_days": backfill_days,
    }
