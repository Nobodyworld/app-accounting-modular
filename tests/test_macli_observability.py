from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from apps.observability.health import HealthReport
from cli.macli import cli


@pytest.fixture(autouse=True)
def reset_health_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure health registry patches do not leak between tests."""

    from cli import macli as macli_module

    original_evaluate = macli_module.health_registry.evaluate

    async def _empty_evaluate() -> list[HealthReport]:
        return []

    monkeypatch.setattr(macli_module.health_registry, "evaluate", _empty_evaluate)
    yield
    monkeypatch.setattr(macli_module.health_registry, "evaluate", original_evaluate)


def test_health_cli_reports_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    from cli import macli as macli_module

    reports = [
        HealthReport(name="database", healthy=True, severity="critical"),
        HealthReport(name="metrics", healthy=True, severity="info"),
    ]

    async def fake_evaluate() -> list[HealthReport]:
        return reports

    monkeypatch.setattr(macli_module, "_register_default_health_checks", lambda: None)
    monkeypatch.setattr(macli_module.health_registry, "evaluate", fake_evaluate)

    runner = CliRunner()
    result = runner.invoke(cli, ["health"])

    assert result.exit_code == 0
    assert "Overall status: ok" in result.output


def test_health_cli_reports_failure_json(monkeypatch: pytest.MonkeyPatch) -> None:
    from cli import macli as macli_module

    reports = [
        HealthReport(
            name="database",
            healthy=False,
            severity="critical",
            details={"error": "boom"},
        )
    ]

    async def fake_evaluate() -> list[HealthReport]:
        return reports

    monkeypatch.setattr(macli_module, "_register_default_health_checks", lambda: None)
    monkeypatch.setattr(macli_module.health_registry, "evaluate", fake_evaluate)

    runner = CliRunner()
    result = runner.invoke(cli, ["health", "--format", "json"])

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["status"] == "degraded"
    assert payload["reports"][0]["details"]["error"] == "boom"


def test_observe_cli_json(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.api.services.extension_loader import ExtensionStatus
    from apps.extensions import ExtensionManifest
    from apps.observability.diagnostics import ObservabilitySnapshot
    from cli import macli as macli_module

    statuses = (
        ExtensionStatus(
            key="observability:demo",
            module="plugins.analytics_baseline.extension",
            manifest=ExtensionManifest(
                key="observability:demo",
                name="Demo",
                version="1.0.0",
                capabilities=("observability",),
            ),
            enabled=True,
        ),
    )

    async def fake_snapshot(*, extension_status_provider):
        return ObservabilitySnapshot(
            generated_at="2024-01-01T00:00:00Z",
            metrics={"lines": 3, "bytes": 128, "checks": ["database"]},
            health={"reports": []},
            incidents=[],
            tracing={"enabled": True, "otel_enabled": False, "exporter": "console"},
            extensions=[{"key": "observability:demo", "loaded": True}],
        )

    monkeypatch.setattr(macli_module, "_register_default_health_checks", lambda: None)
    monkeypatch.setattr(macli_module, "_ensure_extensions_loaded", lambda: statuses)
    monkeypatch.setattr(macli_module, "collect_observability_snapshot", fake_snapshot)

    runner = CliRunner()
    result = runner.invoke(cli, ["observe", "--format", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["metrics"]["lines"] == 3
    assert payload["extensions"][0]["key"] == "observability:demo"
