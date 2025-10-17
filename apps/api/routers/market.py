"""Market data routes."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..db import get_session
from ..services.market_service import MarketService
from ..services.plugin_loader import load_provider

router = APIRouter(prefix="/market", tags=["market"])


@router.post("/sync")
def sync_prices(
    symbol: str,
    start: date,
    end: date,
    provider: str = "plugins.market_yfinance.provider",
    s: Session = Depends(get_session),
) -> dict[str, str | int | date]:
    """Fetch and persist instrument prices for a date range."""

    if start > end:
        raise HTTPException(status_code=400, detail="Start date must be before end date")

    try:
        prov = load_provider(provider)
    except ValueError as exc:  # pragma: no cover - FastAPI integration
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    svc = MarketService(s, prov)
    n = svc.sync_prices(symbol, start, end)
    return {"synced": n, "provider": prov.name, "symbol": symbol, "start": start, "end": end}
