from datetime import UTC, datetime
from decimal import Decimal

from apps.modular_accounting.adapters import (
    InMemoryCommodityAdapter,
    InMemoryFXAdapter,
    InMemoryTaxAdapter,
)
from apps.modular_accounting.application import (
    DataSnapshotService,
    ScenarioSnapshotRunner,
    SnapshotScenario,
)
from apps.modular_accounting.domain import TaxRule
from apps.observability.metrics import metrics_registry


def _service() -> DataSnapshotService:
    fx = InMemoryFXAdapter({"EUR": Decimal("0.93"), "GBP": Decimal("0.79")})
    commodity = InMemoryCommodityAdapter({"XAU": Decimal("2030.45")})
    tax = InMemoryTaxAdapter(
        (
            TaxRule(
                jurisdiction="US",
                rate=Decimal("0.0725"),
                description="Sales tax",
                effective_from=datetime(2023, 1, 1, tzinfo=UTC).date(),
            ),
        )
    )
    return DataSnapshotService(fx_port=fx, commodity_port=commodity, tax_port=tax)


def test_scenario_runner_compiles_summary() -> None:
    service = _service()
    runner = ScenarioSnapshotRunner(service)
    scenarios = [
        SnapshotScenario.from_mapping(
            {
                "name": "usd_metals",
                "base_currency": "USD",
                "commodity_symbols": ["XAU"],
                "jurisdictions": ["US"],
            }
        ),
        SnapshotScenario.from_mapping(
            {
                "name": "eur_fx_only",
                "base_currency": "EUR",
                "commodity_symbols": [],
                "jurisdictions": [],
            }
        ),
    ]

    batch = runner.run(
        scenarios,
        providers={"fx": "stub", "commodity": "stub", "tax": "stub"},
    )

    assert batch.summary.scenario_count == 2
    assert set(batch.summary.base_currencies) == {"USD", "EUR"}
    assert "usd_metals" not in batch.summary.missing_sections
    assert batch.summary.missing_sections["eur_fx_only"] == ("commodities", "tax")
    assert batch.summary.total_fx_rates >= 2
    assert batch.results[0].providers == {
        "fx": "stub",
        "commodity": "stub",
        "tax": "stub",
    }


def test_snapshot_scenario_requires_name() -> None:
    try:
        SnapshotScenario.from_mapping({"base_currency": "USD"})
    except ValueError as exc:
        assert "Scenario name" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("Expected ValueError when name is missing")


def test_scenario_runner_emits_metrics() -> None:
    service = _service()
    runner = ScenarioSnapshotRunner(service)
    scenario = SnapshotScenario.from_mapping(
        {
            "name": "telemetry_probe",
            "base_currency": "USD",
            "commodity_symbols": ["XAU"],
            "jurisdictions": ["US"],
            "tags": ["variance"],
        }
    )

    runner.run([scenario])

    payload = metrics_registry.render_latest().decode()
    assert 'modacct_scenario_runs_total{scenario="telemetry_probe"' in payload
