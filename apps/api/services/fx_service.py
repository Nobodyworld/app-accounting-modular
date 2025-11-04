import logging
from datetime import date

from sqlmodel import Session

from ..models.models import Rate

logger = logging.getLogger(__name__)


class BaseFXProvider:
    name: str

    def sync_daily_rates(self, base: str = "USD", date_: date | None = None) -> list[Rate]:
        raise NotImplementedError


class FXService:
    def __init__(self, session: Session, provider: BaseFXProvider):
        self.s = session
        self.provider = provider

    def sync(self, base: str = "USD", date_: date | None = None) -> int:
        """Sync FX rates from provider."""
        try:
            rates = self.provider.sync_daily_rates(base=base, date_=date_)
            for r in rates:
                self.s.add(r)
            self.s.commit()
            logger.info(f"Synced {len(rates)} FX rates")
            return len(rates)
        except Exception as e:
            self.s.rollback()
            logger.error(f"FX sync failed: {e}")
            raise
