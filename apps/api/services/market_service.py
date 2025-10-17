"""Market data services."""

from __future__ import annotations

from datetime import date
from typing import Iterable

from sqlmodel import Session, select

from ..audit import AuditLogger, apply_creation_metadata
from ..models.models import AuditAction, Instrument, Price

__all__ = ["BaseMarketProvider", "MarketService"]


class BaseMarketProvider:
    """Protocol for market data providers."""

    name: str

    def fetch_prices(self, symbol: str, start: date, end: date) -> Iterable[Price]:
        raise NotImplementedError


class MarketService:
    """Synchronise instrument reference data and daily prices."""

    def __init__(
        self,
        session: Session,
        provider: BaseMarketProvider,
        audit_logger: AuditLogger | None = None,
    ):
        self.s = session
        self.provider = provider
        self.audit = audit_logger or AuditLogger(session)

    def sync_prices(self, symbol: str, start: date, end: date) -> int:
        """Persist price data for ``symbol`` between ``start`` and ``end`` inclusive."""

        stmt = select(Instrument).where(Instrument.symbol == symbol)
        inst = self.s.exec(stmt).one_or_none()
        if inst is None:
            inst = Instrument(symbol=symbol, name=symbol)
            apply_creation_metadata(inst)
            self.s.add(inst)
            self.s.commit()
            self.s.refresh(inst)
            self.audit.log(AuditAction.CREATE, "Instrument", inst.id, after=inst)

        prices = list(self.provider.fetch_prices(symbol, start, end))
        for price in prices:
            price.instrument_id = inst.id
            apply_creation_metadata(price)
            self.s.add(price)
        self.s.commit()
        for price in prices:
            self.s.refresh(price)
        payload = {
            "symbol": symbol,
            "start": start,
            "end": end,
            "provider": self.provider.name,
            "instrument_id": inst.id,
            "prices": [price.model_dump() for price in prices],
        }
        self.audit.log(
            AuditAction.CREATE,
            "Price",
            entity_id=str(inst.id),
            after=payload,
        )
        return len(prices)
