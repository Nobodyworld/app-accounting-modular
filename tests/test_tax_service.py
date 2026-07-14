from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from typing import Any

import pytest
from apps.api.models import AuditAction, TaxRule
from apps.api.services.tax_service import (
    BaseTaxProvider,
    JurisdictionTaxUpdater,
    TaxService,
    default_tax_providers,
)
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select


@contextmanager
def _session() -> Iterator[Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


class _Provider(BaseTaxProvider):
    def __init__(self, rules: list[TaxRule | None], *, name: str = "stub") -> None:
        self.rules = rules
        self.name = name

    def upsert_rules(self):
        return self.rules


class _AuditRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.flushed = False

    def log(
        self,
        action: AuditAction,
        entity_name: str,
        entity_id: str | int | None,
        before: Any = None,
        after: Any = None,
        metadata: dict[str, Any] | None = None,
        asynchronous: bool = False,
    ) -> None:
        self.calls.append(
            {
                "action": action,
                "entity_name": entity_name,
                "entity_id": entity_id,
                "before": before,
                "after": after,
                "metadata": metadata,
                "asynchronous": asynchronous,
            }
        )

    def flush(self, *, wait: bool = True, timeout: float | None = None) -> None:
        del wait, timeout
        self.flushed = True


def test_tax_sync_upserts_and_removes_stale_rules() -> None:
    with _session() as session:
        existing = TaxRule(
            jurisdiction="US",
            scope="vat",
            expression="0.10",
            valid_from=date(2024, 1, 1),
            source="stub",
        )
        obsolete = TaxRule(jurisdiction="MX", scope="vat", expression="0.16", source="stub")
        session.add(existing)
        session.add(obsolete)
        session.commit()

        provider = _Provider(
            [
                TaxRule(
                    jurisdiction="US",
                    scope="vat",
                    expression={"rate": 0.2},
                    valid_from=date(2024, 1, 1),
                    source="stub",
                    precedence=50,
                ),
                TaxRule(
                    jurisdiction="CA",
                    scope="gst",
                    expression="0.05",
                    valid_from=date(2024, 1, 1),
                    source="stub",
                    precedence=50,
                ),
            ]
        )

        service = TaxService(session, provider)
        count = service.sync_rules()

        assert count == 2
        rules = session.exec(select(TaxRule).order_by(TaxRule.jurisdiction)).all()
        assert len(rules) == 2
        updated = next(rule for rule in rules if rule.jurisdiction == "US")
        assert updated.id == existing.id
        assert '"rate": 0.2' in updated.expression
        assert all(rule.jurisdiction != "MX" for rule in rules)


def test_tax_sync_rejects_inverted_validity_window_without_writes() -> None:
    with _session() as session:
        provider = _Provider(
            [
                TaxRule(
                    jurisdiction="US",
                    scope="vat",
                    expression={"rate": 0.2},
                    valid_from=date(2025, 2, 1),
                    valid_to=date(2025, 1, 1),
                )
            ]
        )

        with pytest.raises(ValueError, match="inverted validity window"):
            TaxService(session, provider).sync_rules()

        assert session.exec(select(TaxRule)).all() == []


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        ({"and": "not-a-list"}, "expects a list"),
        ({"gt": "ab"}, "expects a two-item list"),
        ({"gt": [1]}, "expects a two-item list"),
        ({"var": ["amount"]}, "expects a string"),
        ({"rate": True}, "expects a numeric rate"),
        ({"gt": [{"unknown": 1}, 0]}, "Unsupported JSONLogic operator"),
        ({"and": [{"gt": [{"var": "amount"}, 0]}, {"unknown": 1}]}, "Unsupported JSONLogic operator"),
        ({"rate": 0.2, "var": "amount"}, "exactly one operator"),
    ],
)
def test_tax_sync_rejects_malformed_jsonlogic_shapes(expression: dict[str, Any], message: str) -> None:
    with _session() as session:
        provider = _Provider([TaxRule(jurisdiction="US", scope="vat", expression=expression)])

        with pytest.raises(ValueError, match=message):
            TaxService(session, provider).sync_rules()

        assert session.exec(select(TaxRule)).all() == []


def test_tax_sync_rejects_unsupported_jsonlogic_operator() -> None:
    with _session() as session:
        provider = _Provider(
            [
                TaxRule(
                    jurisdiction="US",
                    scope="vat",
                    expression={"unknown": 1},
                    valid_from=date(2024, 1, 1),
                )
            ]
        )
        service = TaxService(session, provider)

        with pytest.raises(ValueError, match="Unsupported JSONLogic operator"):
            service.sync_rules()


def test_tax_sync_rejects_duplicate_provider_keys_before_persistence() -> None:
    with _session() as session:
        provider = _Provider(
            [
                TaxRule(jurisdiction="US", scope="vat", expression={"rate": 0.2}),
                TaxRule(jurisdiction="US", scope="vat", expression={"rate": 0.25}),
            ]
        )

        with pytest.raises(ValueError, match="Duplicate tax rule key for US:vat"):
            TaxService(session, provider, organization_id=7).sync_rules()

        assert session.exec(select(TaxRule)).all() == []


def test_tax_sync_scopes_updates_and_stale_removal_by_organization_and_provider() -> None:
    with _session() as session:
        org_one = TaxRule(
            organization_id=1,
            jurisdiction="US",
            scope="vat",
            expression="0.10",
            valid_from=date(2024, 1, 1),
            source="stub",
        )
        org_one_stale = TaxRule(
            organization_id=1,
            jurisdiction="MX",
            scope="vat",
            expression="0.16",
            source="stub",
        )
        org_two = TaxRule(
            organization_id=2,
            jurisdiction="US",
            scope="vat",
            expression="0.11",
            valid_from=date(2024, 1, 1),
            source="stub",
        )
        other_provider = TaxRule(
            organization_id=1,
            jurisdiction="CA",
            scope="gst",
            expression="0.05",
            source="other",
        )
        session.add_all([org_one, org_one_stale, org_two, other_provider])
        session.commit()

        incoming = TaxRule(
            organization_id=999,
            jurisdiction="US",
            scope="vat",
            expression={"rate": 0.2},
            valid_from=date(2024, 1, 1),
        )
        count = TaxService(session, _Provider([incoming]), organization_id=1).sync_rules()

        rules = session.exec(select(TaxRule)).all()
        assert count == 1
        assert incoming.organization_id == 1
        assert incoming.source == "stub"
        updated = next(rule for rule in rules if rule.organization_id == 1 and rule.source == "stub")
        assert updated.id == org_one.id
        assert '"rate": 0.2' in updated.expression
        assert all(rule.id != org_one_stale.id for rule in rules)
        assert any(rule.id == org_two.id and rule.expression == "0.11" for rule in rules)
        assert any(rule.id == other_provider.id and rule.expression == "0.05" for rule in rules)


def test_empty_provider_removes_only_rules_in_its_scope() -> None:
    with _session() as session:
        scoped = TaxRule(organization_id=1, jurisdiction="US", scope="vat", expression="0.10", source="stub")
        other_org = TaxRule(organization_id=2, jurisdiction="US", scope="vat", expression="0.11", source="stub")
        other_provider = TaxRule(organization_id=1, jurisdiction="CA", scope="gst", expression="0.05", source="other")
        session.add_all([scoped, other_org, other_provider])
        session.commit()

        count = TaxService(session, _Provider([]), organization_id=1).sync_rules()

        rules = session.exec(select(TaxRule)).all()
        assert count == 0
        assert all(rule.id != scoped.id for rule in rules)
        assert any(rule.id == other_org.id for rule in rules)
        assert any(rule.id == other_provider.id for rule in rules)


def test_tax_sync_ignores_none_provider_entries() -> None:
    with _session() as session:
        provider = _Provider([None, TaxRule(jurisdiction="US", scope="vat", expression={"rate": 0.2})])

        count = TaxService(session, provider).sync_rules()

        rules = session.exec(select(TaxRule)).all()
        assert count == 1
        assert len(rules) == 1
        assert rules[0].source == "stub"


def test_tax_sync_rolls_back_updates_and_inserts_when_commit_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    with _session() as session:
        existing = TaxRule(
            jurisdiction="US",
            scope="vat",
            expression="0.10",
            valid_from=date(2024, 1, 1),
            source="stub",
        )
        session.add(existing)
        session.commit()

        provider = _Provider(
            [
                TaxRule(
                    jurisdiction="US",
                    scope="vat",
                    expression={"rate": 0.2},
                    valid_from=date(2024, 1, 1),
                    source="stub",
                ),
                TaxRule(jurisdiction="CA", scope="gst", expression={"rate": 0.05}, source="stub"),
            ]
        )
        audit = _AuditRecorder()
        original_commit = Session.commit

        def fail_commit(self: Session) -> None:
            raise RuntimeError("database unavailable")

        monkeypatch.setattr(Session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="database unavailable"):
            TaxService(session, provider, audit_logger=audit).sync_rules()
        monkeypatch.setattr(Session, "commit", original_commit)

        session.expire_all()
        rules = session.exec(select(TaxRule)).all()
        assert len(rules) == 1
        assert rules[0].id == existing.id
        assert rules[0].expression == "0.10"
        assert audit.calls == []
        assert audit.flushed is False


def test_tax_sync_audit_payload_records_provider_rules_and_removals() -> None:
    with _session() as session:
        stale = TaxRule(
            organization_id=1,
            jurisdiction="MX",
            scope="vat",
            expression="0.16",
            source="stub",
        )
        session.add(stale)
        session.commit()
        stale_id = stale.id
        audit = _AuditRecorder()
        provider = _Provider([TaxRule(jurisdiction="US", scope="vat", expression={"rate": 0.2})])

        count = TaxService(session, provider, audit_logger=audit, organization_id=1).sync_rules()

        assert count == 1
        assert audit.flushed is True
        assert len(audit.calls) == 1
        call = audit.calls[0]
        assert call["action"] == AuditAction.CREATE
        assert call["entity_name"] == "TaxRule"
        assert call["entity_id"] is None
        assert call["asynchronous"] is True
        payload = call["after"]
        assert payload["provider"] == "stub"
        assert payload["removed"] == [stale_id]
        assert len(payload["rules"]) == 1
        assert payload["rules"][0]["organization_id"] == 1
        assert payload["rules"][0]["source"] == "stub"


def test_default_tax_providers_seed_rules_for_all_jurisdictions() -> None:
    providers = default_tax_providers()
    assert "US" in providers and "EU" in providers
    us_provider = providers["US"]
    rules = list(us_provider.upsert_rules())
    assert rules
    assert rules[0].jurisdiction == "US"
    assert rules[0].expression in ({"rate": 0.07}, '{"rate": 0.07}')


def test_jurisdiction_tax_updater_syncs_all_providers() -> None:
    providers = default_tax_providers()
    with _session() as session:
        updater = JurisdictionTaxUpdater(session, providers)
        count = updater.sync_all()
        stored = session.exec(select(TaxRule)).all()
        assert count == len(stored) == 2
