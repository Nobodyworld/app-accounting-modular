"""Foreign-exchange related routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..db import get_session
from ..models.models import User
from ..security import get_current_organization, get_current_user
from ..services.fx_service import FXService
from ..services.plugin_loader import load_provider

router = APIRouter(prefix="/fx", tags=["fx"])


@router.post("/sync")
def sync_fx(
    organization_id: int,
    base: str = "USD",
    provider: str = "plugins.fx_ecb.provider",
    s: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, str | int]:
    """Synchronise the latest FX rates from the configured provider."""

    try:
        prov = load_provider(provider)
    except ValueError as exc:  # pragma: no cover - FastAPI integration
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    org_ctx = get_current_organization(
        organization_id=organization_id, session=s, current_user=current_user
    )
    if not (org_ctx.membership.is_admin or org_ctx.membership.can_manage_fx):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    svc = FXService(s, prov, organization_id=org_ctx.organization.id)
    count = svc.sync(base=base)
    return {"synced": count, "provider": prov.name, "base": base}
