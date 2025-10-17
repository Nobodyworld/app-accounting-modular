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

    def __init__(self, session: Session, provider: BaseTaxProvider, organization_id: int):
        self.s = session
        self.provider = provider
        self.organization_id = organization_id

    def sync_rules(self) -> int:
        """Synchronise tax rules and return the number of records stored."""

        rules = list(self.provider.upsert_rules())
        for rule in rules:
            rule.organization_id = self.organization_id
        self.s.add_all(rules)
        self.s.commit()
        return len(rules)
