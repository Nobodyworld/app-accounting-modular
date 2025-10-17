"""Tax rules service layer."""

from __future__ import annotations

from typing import Iterable

from sqlmodel import Session

from ..audit import AuditLogger, apply_creation_metadata
from ..models.models import AuditAction, TaxRule

__all__ = ["BaseTaxProvider", "TaxService"]


class BaseTaxProvider:
    """Protocol for tax rule providers."""

    name: str

    def upsert_rules(self) -> Iterable[TaxRule]:
        raise NotImplementedError


class TaxService:
    """Persist structured tax rules from remote providers."""

    def __init__(
        self,
        session: Session,
        provider: BaseTaxProvider,
        audit_logger: AuditLogger | None = None,
    ):
        self.s = session
        self.provider = provider
        self.audit = audit_logger or AuditLogger(session)
    def __init__(self, session: Session, provider: BaseTaxProvider, organization_id: int):
        self.s = session
        self.provider = provider
        self.organization_id = organization_id

    def sync_rules(self) -> int:
        """Synchronise tax rules and return the number of records stored."""

        rules = list(self.provider.upsert_rules())
        for rule in rules:
            apply_creation_metadata(rule)
            rule.organization_id = self.organization_id
        self.s.add_all(rules)
        self.s.commit()
        for rule in rules:
            self.s.refresh(rule)
        payload = {
            "provider": self.provider.name,
            "rules": [rule.model_dump() for rule in rules],
        }
        self.audit.log(
            AuditAction.CREATE,
            "TaxRule",
            entity_id=None,
            after=payload,
        )
        return len(rules)
