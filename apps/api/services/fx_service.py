"""Foreign exchange service abstractions."""

from __future__ import annotations

from datetime import date
from typing import Iterable

from sqlmodel import Session

from ..models.models import Rate

__all__ = ["BaseFXProvider", "FXService"]


class BaseFXProvider:
    """Minimal protocol that FX providers must satisfy."""

    name: str

    def sync_daily_rates(self, base: str = "USD", date_: date | None = None) -> Iterable[Rate]:
        raise NotImplementedError


class FXService:
    """Persist FX data sourced from an external provider."""

    def __init__(self, session: Session, provider: BaseFXProvider, organization_id: int):
        self.s = session
        self.provider = provider
        self.organization_id = organization_id

    def sync(self, base: str = "USD", date_: date | None = None) -> int:
        """Fetch rates and persist them, returning the number of rates stored."""

        rates = list(self.provider.sync_daily_rates(base=base, date_=date_))
        for rate in rates:
            rate.organization_id = self.organization_id
        self.s.add_all(rates)
        self.s.commit()
        return len(rates)
