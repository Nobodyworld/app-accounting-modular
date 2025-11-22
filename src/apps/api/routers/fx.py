"""Foreign-exchange related routes."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlmodel import Session

from ..dependencies import session_with_audit_context
from ..models.models import User
from ..security import get_current_organization, get_current_user
from ..services.fx_service import FXService
from ..services.plugin_loader import load_provider

router = APIRouter(prefix="/fx", tags=["fx"])


def _schedule_backfill(service: FXService, base: str, days: int, tasks: BackgroundTasks) -> None:
    for offset in range(1, days + 1):
        backfill_date = date.today() - timedelta(days=offset)
        tasks.add_task(service.sync, base=base, date_=backfill_date)


@router.post("/sync", response_model=None)
def sync_fx(
    organization_id: int,
    background_tasks: BackgroundTasks,
    base: str = "USD",
    provider_key: str = "fx:ecb",
    backfill_days: int = 0,
    session: Session = Depends(session_with_audit_context),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    """Synchronise the latest FX rates from the configured provider."""

    try:
        handle = load_provider(provider_key)
    except ValueError as exc:  # pragma: no cover - FastAPI integration
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    org_ctx = get_current_organization(
        organization_id=organization_id,
        session=session,
        current_user=current_user,
    )
    membership = org_ctx.membership
    if not (membership.is_admin or membership.can_manage_fx):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    service = FXService(
        session,
        handle.instance,
        organization_id=org_ctx.organization.id,
    )
    count = service.sync(base=base)
    if backfill_days > 0 and background_tasks is not None:
        _schedule_backfill(service, base, backfill_days, background_tasks)
    return {
        "synced": count,
        "provider": handle.metadata.name,
        "provider_key": handle.metadata.key,
        "base": base,
        "backfill_days": backfill_days,
    }
