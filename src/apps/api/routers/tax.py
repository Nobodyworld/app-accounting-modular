"""Tax rule synchronisation routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..audit import AuditLogger
from ..dependencies import session_with_audit_context
from ..models.models import User
from ..security import get_current_organization, get_current_user
from ..services.provider_governance_service import ProviderGovernanceError, ProviderGovernanceService
from ..services.tax_service import TaxService

router = APIRouter(prefix="/tax", tags=["tax"])


@router.post("/sync")
def sync_tax(
    organization_id: int,
    provider_key: str = "tax:oecd_demo",
    session: Session = Depends(session_with_audit_context),
    current_user: User = Depends(get_current_user),
) -> dict[str, str | int]:
    """Fetch the latest tax rules from an upstream provider."""

    org_ctx = get_current_organization(organization_id=organization_id, session=session, current_user=current_user)
    if not (org_ctx.membership.is_admin or org_ctx.membership.can_manage_tax):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    try:
        if current_user.id is None or org_ctx.organization.id is None:
            raise HTTPException(status_code=500, detail="Organization context unavailable")
        handle = ProviderGovernanceService(
            session,
            org_ctx.organization.id,
            current_user.id,
        ).resolve_provider("tax", provider_key)
    except ProviderGovernanceError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)}) from exc

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
