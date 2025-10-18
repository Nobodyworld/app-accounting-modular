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
        # TODO - Implement provider-specific price fetching.
        raise NotImplementedError


class MarketService:
    """Synchronise instrument reference data and daily prices."""

    def __init__(
        self,
        session: Session,
        provider: BaseMarketProvider,
        organization_id: int | None = None,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self.session = session
        self.provider = provider
        self.organization_id = organization_id
        self.audit = audit_logger or AuditLogger(session)

    def sync_prices(self, symbol: str, start: date, end: date) -> int:
        """Persist price data for ``symbol`` between ``start`` and ``end`` inclusive."""

        stmt = select(Instrument).where(Instrument.symbol == symbol)
        if self.organization_id is not None:
            stmt = stmt.where(Instrument.organization_id == self.organization_id)
        inst = self.session.exec(stmt).one_or_none()
        if inst is None:
            inst = Instrument(symbol=symbol, name=symbol)
            if self.organization_id is not None:
                inst.organization_id = self.organization_id
            apply_creation_metadata(inst)
            self.session.add(inst)
            try:
                self.session.commit()
            except Exception:
                self.session.rollback()
                raise
            self.session.refresh(inst)
            self.audit.log(AuditAction.CREATE, "Instrument", inst.id, after=inst)

        prices = list(self.provider.fetch_prices(symbol, start, end))
        # TODO - Upsert existing prices instead of blindly inserting duplicates.
        for price in prices:
            price.instrument_id = inst.id
            apply_creation_metadata(price)
            if self.organization_id is not None:
                price.organization_id = self.organization_id
            self.session.add(price)
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        for price in prices:
            self.session.refresh(price)
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
