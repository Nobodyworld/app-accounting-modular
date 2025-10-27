from __future__ import annotations

from fastapi.testclient import TestClient

from apps.api.main import app

client = TestClient(app)


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
