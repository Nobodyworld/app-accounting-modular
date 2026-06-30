from datetime import UTC, datetime
from decimal import Decimal

from apps.api import main as api_main
from apps.api.models.models import User
from apps.api.routers import snapshot as snapshot_router
from apps.api.security import get_current_user
from apps.api.services.snapshot_service import SnapshotResult
from apps.modular_accounting.application import (
    DataSnapshot,
    ScenarioBatchResult,
    ScenarioResult,
    ScenarioSummary,
    SnapshotRequest,
    SnapshotScenario,
    compute_snapshot_diagnostics,
)
from apps.modular_accounting.application.cache import CacheStats
from apps.modular_accounting.domain import CommodityQuote, FXRate, Money, TaxRule
from fastapi.testclient import TestClient


def _result() -> SnapshotResult:
    request = SnapshotRequest(
        base_currency="USD",
        commodity_symbols=("XAU",),
        jurisdictions=("US",),
    )
    snapshot = DataSnapshot(
        fx_rates=(
            FXRate(
                base_currency="USD",
                quote_currency="EUR",
                rate=Decimal("0.92"),
                as_of=datetime(2024, 1, 1, tzinfo=UTC),
            ),
        ),
        commodity_quotes=(
            CommodityQuote(
                symbol="XAU",
                price=Money(amount=Decimal("1944.12"), currency="USD"),
                as_of=datetime(2024, 1, 1, tzinfo=UTC),
            ),
        ),
        tax_rules=(
            TaxRule(
                jurisdiction="US",
                rate=Decimal("0.070"),
                description="Sales tax",
                effective_from=datetime(2023, 1, 1, tzinfo=UTC).date(),
            ),
        ),
    )
    diagnostics = compute_snapshot_diagnostics(
        snapshot,
        request=request,
        now=lambda: datetime(2024, 1, 2, tzinfo=UTC),
        today=lambda: datetime(2024, 1, 2, tzinfo=UTC).date(),
    )
    cache_stats = {
        "fx": CacheStats(size=1, hits=1, misses=0),
        "commodities": CacheStats(size=1, hits=0, misses=0),
        "tax": CacheStats(size=1, hits=0, misses=0),
    }
    providers = {
        "fx": "fx:stub",
        "commodity": "market:stub",
        "tax": "tax:stub",
    }
    return SnapshotResult(
        request=request,
        snapshot=snapshot,
        diagnostics=diagnostics,
        providers=providers,
        cache_stats=cache_stats,
    )


def _batch() -> ScenarioBatchResult:
    result = _result()
    scenario = SnapshotScenario(name="demo", request=result.request, tags=("api",))
    scenario_result = ScenarioResult(
        scenario=scenario,
        snapshot=result.snapshot,
        diagnostics=result.diagnostics,
        cache_stats=result.cache_stats,
        providers=result.providers,
    )
    summary = ScenarioSummary(
        scenario_count=1,
        base_currencies=(scenario.base_currency,),
        commodity_symbols=scenario.commodity_symbols,
        jurisdictions=scenario.jurisdictions or (),
        missing_sections={},
        total_fx_rates=result.diagnostics.fx_rate_count,
        total_commodity_quotes=result.diagnostics.commodity_quote_count,
        total_tax_rules=result.diagnostics.tax_rule_count,
        max_fx_age_seconds=result.diagnostics.fx_max_age_seconds,
        max_commodity_age_seconds=result.diagnostics.commodity_max_age_seconds,
        max_active_tax_rules=result.diagnostics.active_tax_rule_count,
    )
    return ScenarioBatchResult(results=(scenario_result,), summary=summary)


def _create_app_without_db(monkeypatch):
    monkeypatch.setattr(api_main, "init_db", lambda: None)
    return api_main.create_app()


def test_snapshot_endpoint_returns_payload(monkeypatch) -> None:
    app = _create_app_without_db(monkeypatch)

    def _stub_user() -> User:
        return User(
            id=1,
            email="snapshot@example.com",
            password_hash="stub",
            is_active=True,
        )

    class DummyOrchestrator:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def build_snapshot(self, **kwargs):
            self.calls.append(kwargs)
            return _result()

    orchestrator = DummyOrchestrator()
    app.dependency_overrides[snapshot_router.get_snapshot_orchestrator] = lambda: orchestrator
    app.dependency_overrides[get_current_user] = _stub_user

    with TestClient(app) as client:
        response = client.get("/snapshot")
        assert response.status_code == 200
        payload = response.json()
        assert payload["providers"]["fx"] == "fx:stub"
        assert payload["request"]["base_currency"] == "USD"
        assert payload["diagnostics"]["fx_rate_count"] == 1
        assert payload["diagnostics"]["missing_sections"] == []

        response = client.get(
            "/snapshot",
            params={"commodity": ["XAG"], "jurisdiction": ["EU"]},
        )
        assert response.status_code == 200
        assert orchestrator.calls[-1]["commodity_symbols"] == ["XAG"]
        assert orchestrator.calls[-1]["jurisdictions"] == ["EU"]


def test_snapshot_scenarios_endpoint(monkeypatch) -> None:
    app = _create_app_without_db(monkeypatch)

    def _stub_user() -> User:
        return User(
            id=1,
            email="scenario@example.com",
            password_hash="stub",
            is_active=True,
        )

    class DummyOrchestrator:
        def __init__(self) -> None:
            self.calls: list[SnapshotScenario] = []
            self.reset_cache = False

        def run_scenarios(self, scenarios, reset_cache_between_runs: bool = False) -> ScenarioBatchResult:
            self.calls = list(scenarios)
            self.reset_cache = reset_cache_between_runs
            return _batch()

    orchestrator = DummyOrchestrator()
    app.dependency_overrides[snapshot_router.get_snapshot_orchestrator] = lambda: orchestrator
    app.dependency_overrides[get_current_user] = _stub_user

    with TestClient(app) as client:
        response = client.post(
            "/snapshot/scenarios",
            json={
                "reset_cache_between_runs": True,
                "scenarios": [
                    {
                        "name": "demo",
                        "base_currency": "USD",
                        "commodity_symbols": ["XAU"],
                        "jurisdictions": ["US"],
                        "tags": ["api"],
                    }
                ],
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"]["scenario_count"] == 1
        assert payload["results"][0]["providers"]["fx"] == "fx:stub"
        assert orchestrator.reset_cache is True
        assert orchestrator.calls[0].name == "demo"


def test_snapshot_plan_preview_endpoint(monkeypatch) -> None:
    app = _create_app_without_db(monkeypatch)

    def _stub_user() -> User:
        return User(
            id=2,
            email="plan@example.com",
            password_hash="stub",
            is_active=True,
        )

    app.dependency_overrides[get_current_user] = _stub_user

    with TestClient(app) as client:
        response = client.post(
            "/snapshot/plans/preview",
            json={
                "metadata": {"name": "QA Plan", "tags": ["ci"]},
                "defaults": {"base_currency": "USD"},
                "scenarios": [
                    {
                        "name": "baseline",
                        "base_currency": "USD",
                        "commodity_symbols": ["XAU"],
                    },
                    {
                        "name": "eur_fx",
                        "base_currency": "EUR",
                        "commodity_symbols": [],
                        "tags": ["emea"],
                    },
                ],
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["plan"]["metadata"]["name"] == "QA Plan"
        assert payload["summary"]["scenario_count"] == 2
        assert sorted(payload["summary"]["base_currencies"]) == ["EUR", "USD"]
