"""Tax rule synchronisation routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..audit import AuditLogger
from ..db import get_session
from ..models.models import User
from ..security import get_current_organization, get_current_user
from ..services.plugin_loader import load_provider
from ..services.tax_service import TaxService

router = APIRouter(prefix="/tax", tags=["tax"])


@router.post("/sync")
def sync_tax(
    organization_id: int,
    provider_key: str = "tax:oecd_demo",
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, str | int]:
    """Fetch the latest tax rules from an upstream provider."""

    try:
        handle = load_provider(provider_key)
    except ValueError as exc:  # pragma: no cover - FastAPI integration
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    org_ctx = get_current_organization(organization_id=organization_id, session=session, current_user=current_user)
    if not (org_ctx.membership.is_admin or org_ctx.membership.can_manage_tax):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    service = TaxService(
        session,
        handle.instance,
        audit_logger=AuditLogger(session),
        organization_id=org_ctx.organization.id,
    )
    synced = service.sync_rules()
    return {
        "synced": synced,
        "provider": handle.metadata.name,
        "provider_key": handle.metadata.key,
    }
