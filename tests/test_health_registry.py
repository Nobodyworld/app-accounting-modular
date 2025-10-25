from __future__ import annotations

import asyncio

from apps.observability.health import HealthRegistry, HealthReport


def test_health_registry_sync_and_async() -> None:
    registry = HealthRegistry()

    registry.register("sync", lambda: True)

    async def async_check() -> HealthReport:
        await asyncio.sleep(0)
        return HealthReport(name="async", healthy=False, severity="warning")

    registry.register("async", async_check)

    reports = asyncio.run(registry.evaluate())
    names = {report.name for report in reports}
    assert names == {"sync", "async"}
    assert any(not report.healthy for report in reports)

    grouped = asyncio.run(registry.evaluate_by_severity())
    assert "warning" in grouped
    assert len(grouped["warning"]) == 1
