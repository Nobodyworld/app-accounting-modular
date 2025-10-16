from datetime import date
from typing import List
from sqlmodel import Session
from ..models.models import Rate

class BaseFXProvider:
    name: str
    def sync_daily_rates(self, base: str = "USD", date_: date | None = None) -> List[Rate]:
        raise NotImplementedError

class FXService:
    def __init__(self, session: Session, provider: BaseFXProvider):
        self.s = session
        self.provider = provider

    def sync(self, base: str = "USD", date_: date | None = None) -> int:
        rates = self.provider.sync_daily_rates(base=base, date_=date_)
        for r in rates:
            self.s.add(r)
        self.s.commit()
        return len(rates)
