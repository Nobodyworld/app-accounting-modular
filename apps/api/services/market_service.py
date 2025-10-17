from datetime import date
from typing import Sequence

from sqlmodel import Session, select

from ..models.models import Instrument, Price

class BaseMarketProvider:
    name: str

    def fetch_prices(self, symbol: str, start: date, end: date) -> Sequence[Price]:
        raise NotImplementedError

class MarketService:
    def __init__(self, session: Session, provider: BaseMarketProvider):
        self.s = session
        self.provider = provider

    def sync_prices(self, symbol: str, start: date, end: date) -> int:
        symbol_clean = symbol.strip().upper()
        if not symbol_clean:
            raise ValueError("Symbol is required")
        if start > end:
            raise ValueError("Start date must be before or equal to end date")

        stmt = select(Instrument).where(Instrument.symbol == symbol_clean)
        instrument = self.s.exec(stmt).one_or_none()

        if instrument is None:
            instrument = Instrument(symbol=symbol_clean, name=symbol_clean)
            self.s.add(instrument)
            self.s.flush()

        prices = list(self.provider.fetch_prices(symbol_clean, start, end))
        for price in prices:
            price.instrument_id = instrument.id
            price.provider = self.provider.name
            self.s.add(price)

        self.s.commit()
        return len(prices)
