from datetime import date
from typing import Sequence

from sqlmodel import Session

from ..models.models import Rate

class BaseFXProvider:
    name: str
    def sync_daily_rates(self, base: str = "USD", date_: date | None = None) -> Sequence[Rate]:
        raise NotImplementedError

class FXService:
    def __init__(self, session: Session, provider: BaseFXProvider):
        self.s = session
        self.provider = provider

    def sync(self, base: str = "USD", date_: date | None = None) -> int:
        base_clean = base.strip().upper()
        if not base_clean:
            raise ValueError("Base currency is required")

        rates = list(self.provider.sync_daily_rates(base=base_clean, date_=date_))
        for rate in rates:
            rate.base = base_clean
            rate.quote = rate.quote.upper()
            self.s.add(rate)
        self.s.commit()
        return len(rates)
