from datetime import date
from typing import List
from sqlmodel import Session
from ..models.models import Price, Instrument

class BaseMarketProvider:
    name: str
    def fetch_prices(self, symbol: str, start: date, end: date) -> List[Price]:
        raise NotImplementedError

class MarketService:
    def __init__(self, session: Session, provider: BaseMarketProvider):
        self.s = session
        self.provider = provider

    def sync_prices(self, symbol: str, start: date, end: date) -> int:
        # ensure instrument
        inst = self.s.query(Instrument).filter(Instrument.symbol == symbol).first()
        if not inst:
            inst = Instrument(symbol=symbol, name=symbol)
            self.s.add(inst); self.s.commit(); self.s.refresh(inst)
        prices = self.provider.fetch_prices(symbol, start, end)
        for p in prices:
            p.instrument_id = inst.id
            self.s.add(p)
        self.s.commit()
        return len(prices)
