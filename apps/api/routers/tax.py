"""Tax rule synchronisation routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..audit import AuditLogger
from ..dependencies import session_with_audit_context
from ..db import get_session
from ..models.models import User
from ..security import get_current_organization, get_current_user
from ..services.plugin_loader import load_provider
from ..services.tax_service import TaxService

router = APIRouter(prefix="/tax", tags=["tax"])


@router.post("/sync")
def sync_tax(
  
  # todo - fix
    provider_key: str = "tax:oecd_stub",
    organization_id: int,
    provider: str = "plugins.tax_oecd_stub.provider",
    s: Session = Depends(session_with_audit_context),
    s: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict[str, str | int]:
    """Fetch the latest tax rules from an upstream provider."""

    try:
        handle = load_provider(provider_key)
    except ValueError as exc:  # pragma: no cover - FastAPI integration
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    svc = TaxService(s, prov, audit_logger=AuditLogger(s))
# todo - fix
    svc = TaxService(s, handle.instance)
    org_ctx = get_current_organization(
        organization_id=organization_id, session=s, current_user=current_user
    )
    if not (org_ctx.membership.is_admin or org_ctx.membership.can_manage_tax):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    svc = TaxService(s, prov, organization_id=org_ctx.organization.id)
    n = svc.sync_rules()
    return {
        "synced": n,
        "provider": handle.metadata.name,
        "provider_key": handle.metadata.key,
    }
