from __future__ import annotations

import asyncio

import pytest

from apps.observability.metrics import MetricsRegistry, ScenarioTelemetryAdapter


def test_scenario_telemetry_records_success_and_gauge_resets() -> None:
    registry = MetricsRegistry.create()
    adapter = ScenarioTelemetryAdapter(registry)

    with adapter.track(scenario="baseline", tags=("beta", "alpha")):
        pass

    metrics = registry.render_latest().decode()

    assert 'modacct_scenario_runs_total{scenario="baseline",tags="alpha,beta",status="success"} ' "1.0" in metrics
    assert 'modacct_scenario_inflight{scenario="baseline",tags="alpha,beta"} 0.0' in metrics
    assert 'modacct_scenario_latency_seconds{scenario="baseline",tags="alpha,beta",status="success"}' in metrics


def test_scenario_telemetry_records_error_and_resets_gauge() -> None:
    registry = MetricsRegistry.create()
    adapter = ScenarioTelemetryAdapter(registry)

    with pytest.raises(RuntimeError, match="boom"):
        with adapter.track(scenario="unstable"):
            raise RuntimeError("boom")

    metrics = registry.render_latest().decode()

    assert 'modacct_scenario_runs_total{scenario="unstable",tags="<none>",status="error"} ' "1.0" in metrics
    assert 'modacct_scenario_inflight{scenario="unstable",tags="<none>"} 0.0' in metrics


def test_scenario_telemetry_async_records_success() -> None:
    registry = MetricsRegistry.create()
    adapter = ScenarioTelemetryAdapter(registry)

    async def run() -> None:
        async with adapter.track_async(scenario="async-run", tags=("beta",)):
            await asyncio.sleep(0)

    asyncio.run(run())

    metrics = registry.render_latest().decode()

    assert 'modacct_scenario_runs_total{scenario="async-run",tags="beta",status="success"} ' "1.0" in metrics
    assert 'modacct_scenario_inflight{scenario="async-run",tags="beta"} 0.0' in metrics
