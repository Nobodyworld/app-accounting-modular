from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from ..db import get_session
from ..services.market_service import MarketService
from ..services.plugin_loader import load_provider

router = APIRouter(prefix="/market", tags=["market"])

@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
def sync_prices(
    symbol: str,
    start: date,
    end: date,
    provider: str = "plugins.market_yfinance.provider",
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        provider_impl = load_provider(provider)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    service = MarketService(session, provider_impl)
    try:
        count = service.sync_prices(symbol, start, end)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return {"synced": count, "provider": provider_impl.name, "symbol": symbol}
