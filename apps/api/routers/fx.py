"""Foreign-exchange related routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..dependencies import session_with_audit_context
from ..models.models import User
from ..security import get_current_organization, get_current_user
from ..services.fx_service import FXService
from ..services.plugin_loader import load_provider

router = APIRouter(prefix="/fx", tags=["fx"])


@router.post("/sync")
def sync_fx(
    organization_id: int,
    base: str = "USD",
    provider_key: str = "fx:ecb",
    session: Session = Depends(session_with_audit_context),
    current_user: User = Depends(get_current_user),
) -> dict[str, str | int]:
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
    return {
        "synced": count,
        "provider": handle.metadata.name,
        "provider_key": handle.metadata.key,
        "base": base,
    }
