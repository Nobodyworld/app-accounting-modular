"""Market data services."""

from __future__ import annotations

from datetime import date
from typing import Iterable

from sqlmodel import Session, select

from ..models.models import Instrument, Price

__all__ = ["BaseMarketProvider", "MarketService"]


class BaseMarketProvider:
    """Protocol for market data providers."""

    name: str

    def fetch_prices(self, symbol: str, start: date, end: date) -> Iterable[Price]:
        raise NotImplementedError


class MarketService:
    """Synchronise instrument reference data and daily prices."""

    def __init__(self, session: Session, provider: BaseMarketProvider, organization_id: int):
        self.s = session
        self.provider = provider
        self.organization_id = organization_id

    def sync_prices(self, symbol: str, start: date, end: date) -> int:
        """Persist price data for ``symbol`` between ``start`` and ``end`` inclusive."""

        stmt = select(Instrument).where(
            Instrument.symbol == symbol,
            Instrument.organization_id == self.organization_id,
        )
        inst = self.s.exec(stmt).one_or_none()
        if inst is None:
            inst = Instrument(
                symbol=symbol,
                name=symbol,
                organization_id=self.organization_id,
            )
            self.s.add(inst)
            self.s.commit()
            self.s.refresh(inst)

        prices = list(self.provider.fetch_prices(symbol, start, end))
        for price in prices:
            price.instrument_id = inst.id
            price.organization_id = self.organization_id
            self.s.add(price)
        self.s.commit()
        return len(prices)
