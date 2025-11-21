from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.routers import core as core_router
from apps.api.routers import health as health_router
from apps.observability.health import HealthReport, health_registry
from apps.observability.metrics import RequestMetricsMiddleware, metrics_registry

api_app = FastAPI()
api_app.add_middleware(RequestMetricsMiddleware, registry=metrics_registry)
api_app.include_router(core_router.router)
api_app.include_router(health_router.router)

client = TestClient(api_app)


@pytest.fixture(autouse=True)
def _stub_health_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_evaluate() -> list[HealthReport]:
        return [
            HealthReport(
                name="database",
                healthy=True,
                severity="critical",
                details={"status": "ok"},
            ),
            HealthReport(
                name="scheduler",
                healthy=True,
                severity="info",
                details={"running": True, "jobs": 1},
            ),
            HealthReport(
                name="extensions",
                healthy=True,
                severity="info",
                details={"configured": 0, "enabled": 0, "loaded": []},
            ),
        ]

    monkeypatch.setattr(health_registry, "evaluate", _fake_evaluate)


def test_core_health_endpoint_includes_database_and_scheduler() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ok", "degraded", "critical", "unknown"}
    assert isinstance(payload["providers"], list)
    assert "provider_compatibility" in payload
    assert isinstance(payload["checks"], list)
    checks = {entry["name"]: entry for entry in payload["checks"]}
    assert "database" in checks
    assert "scheduler" in checks
    for name in ("database", "scheduler"):
        check = checks[name]
        assert "healthy" in check
        assert "severity" in check
        assert isinstance(check.get("details"), dict)
        summary = payload[name]
        assert summary["name"] == name
        assert summary["details"] == check["details"]


def test_liveness_probe() -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_probe() -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ok", "degraded"}
    assert "reports" in payload


def test_metrics_endpoint() -> None:
    response = client.get("/health/metrics")
    assert response.status_code == 200
    assert "modacct_http_requests_total" in response.text


def test_telemetry_endpoint() -> None:
    response = client.get("/health/telemetry")
    assert response.status_code == 200
    payload = response.json()
    assert payload["metrics"]["lines"] >= 1
    assert any(report["name"] == "extensions" for report in payload["health"])
    assert isinstance(payload["extensions"], list)


def test_providers_endpoint_exposes_compatibility() -> None:
    response = client.get("/providers")
    assert response.status_code == 200
    payload = response.json()
    assert "providers" in payload
    providers = payload["providers"]
    assert isinstance(providers, list)
    if providers:
        compat = providers[0]["compatibility"]
        assert "api_version" in compat
        assert "status" in compat
