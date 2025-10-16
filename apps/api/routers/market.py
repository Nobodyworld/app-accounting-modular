from fastapi import APIRouter, Depends
from sqlmodel import Session
from datetime import date
from ..db import get_session
from ..services.market_service import MarketService
from ..services.plugin_loader import load_provider

router = APIRouter(prefix="/market", tags=["market"])

@router.post("/sync")
def sync_prices(symbol: str, start: date, end: date, provider: str = "plugins.market_yfinance.provider", s: Session = Depends(get_session)):
    prov = load_provider(provider)
    svc = MarketService(s, prov)
    n = svc.sync_prices(symbol, start, end)
    return {"synced": n, "provider": prov.name, "symbol": symbol}
