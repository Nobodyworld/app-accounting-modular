from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from apps.api.models import TaxRule
from apps.api.services.tax_service import (
    BaseTaxProvider,
    JurisdictionTaxUpdater,
    TaxService,
    default_tax_providers,
)


def _session() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    return Session(engine, expire_on_commit=False)


class _Provider(BaseTaxProvider):
    def __init__(self, rules: list[TaxRule]) -> None:
        self.rules = rules
        self.name = "stub"

    def upsert_rules(self):
        return self.rules


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
