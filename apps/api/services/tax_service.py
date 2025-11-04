"""Tax rule ingestion services."""

from __future__ import annotations

from collections.abc import Iterable

from sqlmodel import Session

from ..audit import AuditLogger, apply_creation_metadata
from ..models.models import AuditAction, TaxRule

__all__ = ["BaseTaxProvider", "TaxService"]


class BaseTaxProvider:
    """Protocol for tax rule providers."""

    name: str

    def upsert_rules(self) -> Iterable[TaxRule]:  # pragma: no cover - interface contract
        # TODO - Implement provider-specific tax rule upsert logic.
        raise NotImplementedError


class TaxService:
    """Persist structured tax rules from remote providers."""

    def __init__(
        self,
        session: Session,
        provider: BaseTaxProvider,
        *,
        audit_logger: AuditLogger | None = None,
        organization_id: int | None = None,
    ) -> None:
        self.session = session
        self.provider = provider
        self.audit = audit_logger or AuditLogger(session)
        self.organization_id = organization_id

    def sync_rules(self) -> int:
        """Synchronise tax rules and return the number of records stored."""

        rules = list(self.provider.upsert_rules())
        for rule in rules:
            apply_creation_metadata(rule)
            if self.organization_id is not None:
                rule.organization_id = self.organization_id

        try:
            self.session.add_all(rules)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        for rule in rules:
            self.session.refresh(rule)
        # TODO - Remove stale rules that were not returned by the provider sync.

        payload = {
            "provider": getattr(self.provider, "name", "unknown"),
            "rules": [rule.model_dump() for rule in rules],
        }
        self.audit.log(
            AuditAction.CREATE,
            "TaxRule",
            entity_id=None,
            after=payload,
        )
        return len(rules)
