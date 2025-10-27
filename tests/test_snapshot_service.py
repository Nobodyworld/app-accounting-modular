from datetime import date

from apps.api.models.models import Price, Rate
from apps.api.models.models import TaxRule as DBTaxRule
from apps.api.services.plugin_loader import ProviderHandle, ProviderMetadata
from apps.api.services.snapshot_service import (
    SnapshotOrchestrator,
    scenario_batch_to_payload,
)
from apps.modular_accounting.application import SnapshotScenario


class StubFXProvider:
    name = "fx_stub"

    def sync_daily_rates(self, base: str = "USD", date_=None):
        return [
            Rate(
                base=base,
                quote="EUR",
                date=date(2024, 1, 1),
                value=0.92,
                provider=self.name,
            ),
            Rate(
                base=base,
                quote="GBP",
                date=date(2024, 1, 1),
                value=0.78,
                provider=self.name,
            ),
        ]


class StubMarketProvider:
    name = "market_stub"

    def fetch_prices(self, symbol: str, start: date, end: date):
        return [
            Price(instrument_id=1, date=start, close=100.0, provider=self.name),
            Price(instrument_id=1, date=end, close=125.5, provider=self.name),
        ]


class StubTaxProvider:
    name = "tax_stub"

    def upsert_rules(self):
        return [
            DBTaxRule(
                jurisdiction="US",
                scope="sales",
                expression="rate=0.07",
                valid_from=date(2023, 1, 1),
                source="stub",
            ),
            DBTaxRule(
                jurisdiction="EU",
                scope="vat",
                expression="rate=0.20",
                valid_from=date(2022, 6, 1),
            ),
        ]


def _handle(key: str, capability: str, provider) -> ProviderHandle:
    metadata = ProviderMetadata(
        key=key,
        name=f"Stub {capability}",
        description=None,
        capabilities=(capability,),
    )
    return ProviderHandle(instance=provider, metadata=metadata)


def _resolver():
    handles = {
        "fx:stub": _handle("fx:stub", "fx", StubFXProvider()),
        "market:stub": _handle("market:stub", "market", StubMarketProvider()),
        "tax:stub": _handle("tax:stub", "tax", StubTaxProvider()),
    }

    def load(key: str) -> ProviderHandle:
        return handles[key]

    def catalog(capability: str | None = None):
        values = []
        for handle in handles.values():
            if capability is None or capability in handle.metadata.capabilities:
                values.append(handle.metadata)
        return values

    return load, catalog


def test_snapshot_orchestrator_builds_snapshot() -> None:
    load, catalog = _resolver()
    orchestrator = SnapshotOrchestrator(
        provider_loader=load,
        provider_catalog=catalog,
        commodity_lookback_days=2,
    )

    result = orchestrator.build_snapshot(
        base_currency="USD",
        commodity_symbols=("XAU",),
        jurisdictions=("US",),
    )

    assert result.request.base_currency == "USD"
    assert result.snapshot.fx_rates[0].quote_currency == "EUR"
    assert result.snapshot.commodity_quotes[0].symbol == "XAU"
    assert {rule.jurisdiction for rule in result.snapshot.tax_rules} == {"US"}
    assert result.diagnostics.fx_rate_count == 2
    assert "fx" not in result.diagnostics.missing_sections
    payload = result.as_payload()
    assert payload["providers"]["fx"] == "fx:stub"
    assert payload["request"]["commodity_symbols"] == ["XAU"]
    assert payload["diagnostics"]["commodity_quote_count"] == 1


def test_snapshot_orchestrator_runs_scenarios() -> None:
    load, catalog = _resolver()
    orchestrator = SnapshotOrchestrator(
        provider_loader=load,
        provider_catalog=catalog,
        commodity_lookback_days=2,
    )

    scenarios = [
        SnapshotScenario.from_mapping(
            {
                "name": "metals",
                "base_currency": "USD",
                "commodity_symbols": ["XAU"],
                "jurisdictions": ["US"],
            }
        ),
        SnapshotScenario.from_mapping(
            {
                "name": "fx_only",
                "base_currency": "USD",
                "commodity_symbols": [],
                "jurisdictions": [],
            }
        ),
    ]

    batch = orchestrator.run_scenarios(scenarios)

    assert batch.summary.scenario_count == 2
    assert "fx_only" in batch.summary.missing_sections
    assert batch.results[0].providers["fx"] == "fx:stub"

    payload = scenario_batch_to_payload(batch)
    assert payload["summary"]["scenario_count"] == 2
    assert payload["results"][0]["name"] == "metals"
    assert payload["results"][1]["providers"]["tax"] == "tax:stub"
