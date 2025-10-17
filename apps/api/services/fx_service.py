"""Foreign exchange service abstractions."""

from __future__ import annotations

from datetime import date
from typing import Iterable

from sqlmodel import Session

from ..audit import AuditLogger, apply_creation_metadata
from ..models.models import AuditAction, Rate

__all__ = ["BaseFXProvider", "FXService"]


class BaseFXProvider:
    """Minimal protocol that FX providers must satisfy."""

    name: str

    def sync_daily_rates(self, base: str = "USD", date_: date | None = None) -> Iterable[Rate]:
        raise NotImplementedError


class FXService:
    """Persist FX data sourced from an external provider."""

    def __init__(
        self,
        session: Session,
        provider: BaseFXProvider,
        organization_id: int | None = None,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self.session = session
        self.provider = provider
        self.organization_id = organization_id
        self.audit = audit_logger or AuditLogger(session)

    def sync(self, base: str = "USD", date_: date | None = None) -> int:
        """Fetch rates and persist them, returning the number of rates stored."""

        rates = list(self.provider.sync_daily_rates(base=base, date_=date_))
        for rate in rates:
            apply_creation_metadata(rate)
            if self.organization_id is not None and hasattr(rate, "organization_id"):
                rate.organization_id = self.organization_id

        try:
            self.session.add_all(rates)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise

        for rate in rates:
            self.session.refresh(rate)
        payload = {
            "base": base,
            "date": date_,
            "provider": self.provider.name,
            "rates": [rate.model_dump() for rate in rates],
        }
        self.audit.log(
            AuditAction.CREATE,
            "Rate",
            entity_id=None,
            after=payload,
        )
        return len(rates)
