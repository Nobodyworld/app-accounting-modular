"""Market data routes."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..dependencies import session_with_audit_context
from ..models.models import User
from ..security import get_current_organization, get_current_user
from ..services.market_service import MarketService
from ..services.plugin_loader import load_provider

router = APIRouter(prefix="/market", tags=["market"])


@router.post("/sync")
def sync_prices(
    organization_id: int,
    symbol: str,
    start: date,
    end: date,
    provider_key: str = "market:yfinance",
    session: Session = Depends(session_with_audit_context),
    current_user: User = Depends(get_current_user),
) -> dict[str, str | int | date]:
    """Fetch and persist instrument prices for a date range."""

    if start > end:
        raise HTTPException(status_code=400, detail="Start date must be before end date")

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
    if not (membership.is_admin or membership.can_manage_market):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    service = MarketService(
        session,
        handle.instance,
        organization_id=org_ctx.organization.id,
    )
    n = service.sync_prices(symbol, start, end)
    return {
        "synced": n,
        "provider": handle.metadata.name,
        "provider_key": handle.metadata.key,
        "symbol": symbol,
        "start": start,
        "end": end,
    }
