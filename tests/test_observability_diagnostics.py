from __future__ import annotations

import asyncio

import pytest
from apps.observability.diagnostics import collect_observability_snapshot
from apps.observability.health import HealthReport


class _StubHealthRegistry:
    def __init__(self, reports: list[HealthReport]) -> None:
        self._reports = reports

    async def evaluate(self) -> list[HealthReport]:
        return self._reports

    def list_checks(self) -> list[str]:
        return [report.name for report in self._reports]


class _StubMetricsRegistry:
    def render_latest(self) -> bytes:
        return b"demo_metric 1.0\n"


class _StubTracingConfig:
    def __init__(self, exporter: str, endpoint: str | None = None) -> None:
        self.exporter = exporter
        self.endpoint = endpoint
        self.otel_enabled = bool(endpoint)


class _ExtensionStatus:
    def __init__(self, key: str, module: str, enabled: bool, loaded: bool, capabilities: tuple[str, ...]) -> None:
        self.key = key
        self.module = module
        self.enabled = enabled
        self.manifest = type("Manifest", (), {"capabilities": capabilities})() if loaded else None


@pytest.mark.asyncio
def test_collect_observability_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    reports = [
        HealthReport(name="database", healthy=False, severity="critical", details={"error": "down"}),
        HealthReport(name="metrics", healthy=True, severity="info", details={}),
    ]
    monkeypatch.setattr(
        "apps.observability.diagnostics.health_registry",
        _StubHealthRegistry(reports),
    )
    monkeypatch.setattr(
        "apps.observability.diagnostics.metrics_registry",
        _StubMetricsRegistry(),
    )
    monkeypatch.setattr(
        "apps.observability.diagnostics.get_tracing_config",
        lambda: _StubTracingConfig("console", endpoint="http://localhost:4318"),
    )
    monkeypatch.setattr("apps.observability.diagnostics.is_tracing_enabled", lambda: True)

    statuses = [_ExtensionStatus("ops:heartbeat", "plugins.ops_heartbeat.extension", True, True, ("operations",))]

    snapshot = asyncio.run(
        collect_observability_snapshot(
            extension_status_provider=lambda: statuses,
        )
    )

    assert snapshot.metrics["lines"] == 1
    assert snapshot.health["by_severity"]["critical"]["open"] == 1
    assert snapshot.incidents[0]["action"].startswith("Verify the database service")
    assert snapshot.tracing["endpoint"] == "http://localhost:4318"
    assert snapshot.extensions[0]["key"] == "ops:heartbeat"
