"""Tax rule ingestion services."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from json import dumps
from typing import Any

from sqlmodel import Session, select

from ..audit import AuditLogger, apply_creation_metadata
from ..models.models import AuditAction, TaxRule

JSONLogicRule = Mapping[str, Any]


__all__ = ["BaseTaxProvider", "TaxService"]
_DEFAULT_JURISDICTION_RULES = {
    "US": [
        {
            "jurisdiction": "US",
            "scope": "sales",
            "rate": 0.07,
            "description": "Default US sales tax",
        },
    ],
    "EU": [
        {
            "jurisdiction": "EU",
            "scope": "vat",
            "rate": 0.20,
            "description": "EU VAT baseline",
        }
    ],
}


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
        self._expression_type: str = "jsonlogic"

    @staticmethod
    def _validate_jsonlogic(expr: Mapping[str, Any], *, path: str = "expr") -> None:
        """Shallow validation of supported JSONLogic operators for tax rules."""

        allowed = {"and", "or", "if", "gt", "lt", "le", "ge", "eq", "var", "rate", "and_", "or_", "if_"}
        for key, value in expr.items():
            normalised_key = key.rstrip("_")
            if normalised_key not in allowed:
                raise ValueError(f"Unsupported JSONLogic operator '{key}' at {path}")
            if normalised_key in {"and", "or", "if"}:
                if not isinstance(value, Sequence):
                    raise ValueError(f"Operator '{key}' expects a list at {path}")
                for idx, part in enumerate(value):
                    if isinstance(part, Mapping):
                        TaxService._validate_jsonlogic(part, path=f"{path}.{key}[{idx}]")
                continue
            if normalised_key in {"gt", "lt", "le", "ge", "eq"}:
                if not (isinstance(value, Sequence) and len(value) == 2):
                    raise ValueError(f"Operator '{key}' expects a two-item list at {path}")
                continue
            if normalised_key == "var" and not isinstance(value, str):
                raise ValueError(f"Operator '{key}' expects a string at {path}")
            if normalised_key == "rate" and not isinstance(value, (int, float)):
                raise ValueError(f"Operator '{key}' expects a numeric rate at {path}")

    @classmethod
    def _normalise_expression(cls, expr: object) -> str:
        if isinstance(expr, str):
            return expr
        if isinstance(expr, Mapping):
            cls._validate_jsonlogic(expr)
            return dumps(expr, sort_keys=True)
        msg = "Tax rule expression must be a string or JSON-serialisable mapping"
        raise ValueError(msg)

    def sync_rules(self) -> int:
        """Synchronise tax rules and return the number of records stored."""

        incoming_rules = list(self.provider.upsert_rules())
        scoped_rules = [rule for rule in incoming_rules if rule is not None]
        for rule in scoped_rules:
            apply_creation_metadata(rule)
            if self.organization_id is not None:
                rule.organization_id = self.organization_id
            if getattr(rule, "source", None) is None:
                rule.source = getattr(self.provider, "name", "unknown")
            if getattr(rule, "precedence", None) is None:
                rule.precedence = 100
            if rule.valid_from and rule.valid_to and rule.valid_from > rule.valid_to:
                raise ValueError(f"Tax rule {rule.jurisdiction}:{rule.scope} has inverted validity window")
            try:
                rule.expression = self._normalise_expression(rule.expression)
            except ValueError as exc:
                detail = f"{rule.jurisdiction}:{rule.scope}"
                raise ValueError(f"Invalid expression for {detail} - {exc}") from exc

        stmt = select(TaxRule)
        if self.organization_id is not None:
            stmt = stmt.where(TaxRule.organization_id == self.organization_id)
        provider_name = getattr(self.provider, "name", None)
        if provider_name:
            stmt = stmt.where(TaxRule.source == provider_name)

        existing_rules = list(self.session.exec(stmt))

        existing_index: dict[tuple[Any, ...], TaxRule] = {}
        for db_rule in existing_rules:
            key = (
                db_rule.organization_id,
                db_rule.jurisdiction,
                db_rule.scope,
                db_rule.valid_from,
                db_rule.valid_to,
                db_rule.source,
            )
            existing_index[key] = db_rule
        seen_keys: set[tuple[Any, ...]] = set()

        for rule in scoped_rules:
            key = (
                rule.organization_id,
                rule.jurisdiction,
                rule.scope,
                rule.valid_from,
                rule.valid_to,
                rule.source,
            )
            seen_keys.add(key)
            if key in existing_index:
                db_rule = existing_index[key]
                db_rule.expression = rule.expression
                db_rule.rule_metadata = rule.rule_metadata
                db_rule.precedence = rule.precedence
                db_rule.valid_from = rule.valid_from
                db_rule.valid_to = rule.valid_to
                apply_creation_metadata(db_rule)
            else:
                self.session.add(rule)

        # Remove stale rules that are no longer returned
        stale = [rule for key, rule in existing_index.items() if key not in seen_keys]
        for stale_rule in stale:
            self.session.delete(stale_rule)

        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        for rule in scoped_rules:
            if rule.id is None:
                continue
            self.session.refresh(rule)

        payload = {
            "provider": getattr(self.provider, "name", "unknown"),
            "rules": [rule.model_dump() for rule in scoped_rules],
            "removed": [rule.id for rule in stale if rule.id is not None],
        }
        self.audit.log(
            AuditAction.CREATE,
            "TaxRule",
            entity_id=None,
            after=payload,
            asynchronous=True,
        )
        self.audit.flush()
        return len(scoped_rules)


class JurisdictionTaxUpdater:
    """Coordinate tax rule updates for known jurisdictions using configured providers."""

    def __init__(
        self,
        session: Session,
        provider_factory: Mapping[str, BaseTaxProvider],
        *,
        organization_id: int | None = None,
    ) -> None:
        self.session = session
        self.provider_factory = provider_factory
        self.organization_id = organization_id

    def sync_all(self) -> int:
        """Synchronise rules for all configured jurisdictions."""

        total = 0
        for _jurisdiction, provider in self.provider_factory.items():
            service = TaxService(self.session, provider, organization_id=self.organization_id)
            total += service.sync_rules()
        return total


def default_tax_providers() -> dict[str, BaseTaxProvider]:
    """Return static providers suitable for baseline jurisdiction updates."""

    class _StaticProvider(BaseTaxProvider):
        def __init__(self, name: str, rules: Sequence[dict[str, Any]]) -> None:
            self.name = name
            self._rules = rules

        def upsert_rules(self) -> Iterable[TaxRule]:
            rules: list[TaxRule] = []
            for payload in self._rules:
                rate = payload["rate"]
                rules.append(
                    TaxRule(
                        jurisdiction=payload["jurisdiction"],
                        scope=payload["scope"],
                        expression=dumps({"rate": rate}, sort_keys=True),
                        valid_from=payload.get("valid_from"),
                        valid_to=payload.get("valid_to"),
                        source=payload.get("source", self.name),
                        precedence=payload.get("precedence", 100),
                        rule_metadata=(
                            {"description": payload.get("description")}
                            if payload.get("description") is not None
                            else None
                        ),
                    )
                )
            return rules

    providers: dict[str, BaseTaxProvider] = {}
    for jurisdiction, rules in _DEFAULT_JURISDICTION_RULES.items():
        providers[jurisdiction] = _StaticProvider(f"{jurisdiction.lower()}_tax_provider", rules)
    return providers
