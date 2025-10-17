"""Tax rules service layer."""

from __future__ import annotations

from typing import Iterable

from sqlmodel import Session

from ..models.models import TaxRule

__all__ = ["BaseTaxProvider", "TaxService"]


class BaseTaxProvider:
    """Protocol for tax rule providers."""

    name: str

    def upsert_rules(self) -> Iterable[TaxRule]:
        raise NotImplementedError


class TaxService:
    """Persist structured tax rules from remote providers."""

    def __init__(self, session: Session, provider: BaseTaxProvider):
        self.s = session
        self.provider = provider

    def sync_rules(self) -> int:
        """Synchronise tax rules and return the number of records stored."""

        rules = list(self.provider.upsert_rules())
        self.s.add_all(rules)
        self.s.commit()
        return len(rules)
