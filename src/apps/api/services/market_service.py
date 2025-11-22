from __future__ import annotations

from datetime import date
from time import perf_counter

from sqlmodel import Session, select

from ..audit import AuditAction, AuditLogger, apply_creation_metadata
from ..models.models import Instrument, Price


class BaseMarketProvider:
    name: str

    def fetch_prices(self, symbol: str, start: date, end: date) -> list[Price]:
        raise NotImplementedError


class MarketService:
    def __init__(
        self,
        session: Session,
        provider: BaseMarketProvider,
        *,
        audit_logger: AuditLogger | None = None,
        organization_id: int | None = None,
    ):
        self.s = session
        self.provider = provider
        self.audit = audit_logger or AuditLogger(session)
        self.organization_id = organization_id

    def sync_prices(self, symbol: str, start: date, end: date) -> int:
        stmt = select(Instrument).where(Instrument.symbol == symbol)
        if self.organization_id is not None:
            stmt = stmt.where(Instrument.organization_id == self.organization_id)
        inst = self.s.exec(stmt).first()
        if not inst:
            inst = Instrument(symbol=symbol, name=symbol, organization_id=self.organization_id)
            apply_creation_metadata(inst)
            self.s.add(inst)
            self.s.commit()
            self.s.refresh(inst)
        inst_id = inst.id
        if inst_id is None:
            raise ValueError("Instrument failed to persist")
        start_time = perf_counter()
        prices = list(self.provider.fetch_prices(symbol, start, end))
        try:
            for price in prices:
                price.instrument_id = int(inst_id)
                apply_creation_metadata(price)
                self.s.add(price)
            self.s.commit()
        except Exception:
            self.s.rollback()
            raise
        for price in prices:
            self.s.refresh(price)
        payload = {
            "provider": getattr(self.provider, "name", "unknown"),
            "symbol": symbol,
            "count": len(prices),
        }
        duration = perf_counter() - start_time
        payload["latency_seconds"] = duration
        self.audit.log(AuditAction.CREATE, "Price", entity_id=None, after=payload)
        return len(prices)
