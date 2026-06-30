from __future__ import annotations

import asyncio

import pytest
from apps.observability.health import HealthRegistry, HealthReport
from apps.observability.metrics import HealthTelemetryAdapter, MetricsRegistry


class _TelemetryStub:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def record_evaluation(self, **payload: object) -> None:  # type: ignore[override]
        self.records.append(payload)


def test_health_registry_emits_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = HealthRegistry()
    telemetry = _TelemetryStub()
    monkeypatch.setattr("apps.observability.metrics.health_telemetry", telemetry)

    registry.register("database", lambda: HealthReport(name="database", healthy=True, severity="info"), severity="info")
    reports = asyncio.run(registry.evaluate())

    assert reports == [HealthReport(name="database", healthy=True, severity="info", details={})]
    assert telemetry.records[0]["status"] == "completed"
    assert telemetry.records[0]["healthy"] is True
    assert telemetry.records[0]["severity"] == "info"


def test_health_registry_records_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = HealthRegistry()
    telemetry = _TelemetryStub()
    monkeypatch.setattr("apps.observability.metrics.health_telemetry", telemetry)

    def _boom() -> bool:
        raise RuntimeError("probe failed")

    registry.register("extensions", _boom, severity="warning")
    reports = asyncio.run(registry.evaluate())

    assert reports[0].healthy is False
    assert reports[0].details["error"] == "probe failed"
    assert telemetry.records[0]["status"] == "exception"
    assert telemetry.records[0]["healthy"] is False
    assert telemetry.records[0]["severity"] == "warning"


def test_health_telemetry_adapter_updates_metrics() -> None:
    registry = MetricsRegistry.create()
    adapter = HealthTelemetryAdapter(registry)

    adapter.record_evaluation(
        check="database",
        severity="critical",
        status="completed",
        healthy=True,
        duration=0.42,
    )

    payload = registry.render_latest().decode()
    assert 'modacct_health_checks_total{check="database",severity="critical",status="completed"} 1.0' in payload
    assert 'modacct_health_check_status{check="database",severity="critical"} 1.0' in payload
