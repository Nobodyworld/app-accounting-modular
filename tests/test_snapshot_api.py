from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from apps.api.main import create_app
from apps.api.routers import snapshot as snapshot_router
from apps.api.services.snapshot_service import SnapshotResult
from apps.api.models.models import User
from apps.api.security import get_current_user
from apps.modular_accounting.application import DataSnapshot, SnapshotRequest
from apps.modular_accounting.application.cache import CacheStats
from apps.modular_accounting.domain import CommodityQuote, FXRate, Money, TaxRule


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
        providers=providers,
        cache_stats=cache_stats,
    )


def test_snapshot_endpoint_returns_payload(monkeypatch) -> None:
    app = create_app()

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
    app.dependency_overrides[
        snapshot_router.get_snapshot_orchestrator
    ] = lambda: orchestrator
    app.dependency_overrides[get_current_user] = _stub_user

    client = TestClient(app)
    response = client.get("/snapshot")
    assert response.status_code == 200
    payload = response.json()
    assert payload["providers"]["fx"] == "fx:stub"
    assert payload["request"]["base_currency"] == "USD"

    response = client.get(
        "/snapshot",
        params={"commodity": ["XAG"], "jurisdiction": ["EU"]},
    )
    assert response.status_code == 200
    assert orchestrator.calls[-1]["commodity_symbols"] == ["XAG"]
    assert orchestrator.calls[-1]["jurisdictions"] == ["EU"]
