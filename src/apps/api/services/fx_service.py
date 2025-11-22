from __future__ import annotations

import logging
from datetime import date
from time import perf_counter

from sqlmodel import Session

from ..audit import AuditAction, AuditLogger, apply_creation_metadata
from ..models.models import Rate

logger = logging.getLogger(__name__)


class BaseFXProvider:
    name: str

    def sync_daily_rates(self, base: str = "USD", date_: date | None = None) -> list[Rate]:
        raise NotImplementedError


class FXService:
    def __init__(
        self,
        session: Session,
        provider: BaseFXProvider,
        *,
        audit_logger: AuditLogger | None = None,
        organization_id: int | None = None,
    ):
        self.s = session
        self.provider = provider
        self.audit = audit_logger or AuditLogger(session)
        self.organization_id = organization_id

    def sync(self, base: str = "USD", date_: date | None = None) -> int:
        """Sync FX rates from provider."""
        try:
            start = perf_counter()
            rates = list(self.provider.sync_daily_rates(base=base, date_=date_))
            for rate in rates:
                apply_creation_metadata(rate)
                self.s.add(rate)
            self.s.commit()
            for rate in rates:
                self.s.refresh(rate)
            payload = {
                "provider": getattr(self.provider, "name", "unknown"),
                "base": base,
                "rates": [rate.model_dump() for rate in rates],
            }
            self.audit.log(AuditAction.CREATE, "Rate", entity_id=None, after=payload)
            duration = perf_counter() - start
            logger.info("Synced %s FX rates", len(rates), extra={"latency_seconds": duration})
            return len(rates)
        except Exception as exc:
            self.s.rollback()
            logger.error("FX sync failed: %s", exc)
            raise
