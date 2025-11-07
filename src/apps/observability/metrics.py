"""Prometheus-compatible metrics primitives and FastAPI middleware."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Protocol

try:  # pragma: no cover - prefer real library when available
    from prometheus_client import (  # type: ignore[import]
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )
except Exception:  # pragma: no cover - fallback for air-gapped environments
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4; charset=utf-8"

    class CollectorRegistry:  # type: ignore[override]
        def __init__(self) -> None:
            self._metrics: list[_BaseMetric] = []

        def register(self, metric: _BaseMetric) -> None:
            self._metrics.append(metric)

        @property
        def metrics(self) -> list[_BaseMetric]:
            return self._metrics

    class _MetricHandle:
        def __init__(self, metric: _BaseMetric, key: tuple[str, ...]) -> None:
            self._metric = metric
            self._key = key

        def inc(self, amount: float = 1.0) -> None:
            self._metric._add(self._key, amount)

        def observe(self, value: float) -> None:
            self._metric._add(self._key, value)

        def set(self, value: float) -> None:
            self._metric._set(self._key, value)

        def track_inprogress(self) -> _InProgressTracker:
            return _InProgressTracker(self._metric, self._key)

    class _BaseMetric:
        def __init__(
            self,
            name: str,
            documentation: str,
            labelnames: tuple[str, ...],
            registry: CollectorRegistry,
        ) -> None:
            self.name = name
            self.documentation = documentation
            self._labelnames = labelnames
            self._values: dict[tuple[str, ...], float] = {}
            registry.register(self)

        def labels(self, **labels: str) -> _MetricHandle:
            key = tuple(str(labels.get(label, "")) for label in self._labelnames)
            if key not in self._values:
                self._values[key] = 0.0
            return _MetricHandle(self, key)

        def _add(self, key: tuple[str, ...], amount: float) -> None:
            self._values[key] = self._values.get(key, 0.0) + amount

        def _set(self, key: tuple[str, ...], value: float) -> None:
            self._values[key] = value

    class _InProgressTracker:
        def __init__(self, metric: Gauge, key: tuple[str, ...]) -> None:
            self._metric = metric
            self._key = key

        def __enter__(self) -> None:
            self._metric._add(self._key, 1.0)

        def __exit__(self, exc_type, exc, tb) -> None:
            self._metric._add(self._key, -1.0)

    class Counter(_BaseMetric):  # type: ignore[override]
        def __init__(
            self,
            name: str,
            documentation: str,
            *,
            labelnames: tuple[str, ...],
            registry: CollectorRegistry,
        ) -> None:
            super().__init__(name, documentation, labelnames, registry)

    class Gauge(_BaseMetric):  # type: ignore[override]
        def __init__(
            self,
            name: str,
            documentation: str,
            *,
            labelnames: tuple[str, ...],
            registry: CollectorRegistry,
        ) -> None:
            super().__init__(name, documentation, labelnames, registry)

    class Histogram(_BaseMetric):  # type: ignore[override]
        def __init__(
            self,
            name: str,
            documentation: str,
            *,
            labelnames: tuple[str, ...],
            registry: CollectorRegistry,
            buckets: tuple[float, ...] | None = None,
        ) -> None:
            super().__init__(name, documentation, labelnames, registry)
            self._buckets = buckets or ()

    def generate_latest(registry: CollectorRegistry) -> bytes:  # type: ignore[override]
        lines: list[str] = []
        for metric in registry.metrics:
            for key, value in metric._values.items():
                labels = ",".join(f'{name}="{val}"' for name, val in zip(metric._labelnames, key, strict=False) if name)
                label_str = f"{{{labels}}}" if labels else ""
                lines.append(f"{metric.name}{label_str} {value}")
        return ("\n".join(lines) + "\n").encode()


from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class CacheObserverProtocol(Protocol):
    """Subset of :class:`TTLCache` observer callbacks used for metrics."""

    def record_hit(self) -> None:  # pragma: no cover - delegation to gauges
        """Record that a cache lookup resulted in a hit."""

    def record_miss(self) -> None:  # pragma: no cover - delegation to gauges
        """Record that a cache lookup resulted in a miss."""

    def record_size(self, size: int) -> None:  # pragma: no cover - delegation
        """Record the current size of the cache."""


__all__ = [
    "MetricsRegistry",
    "metrics_registry",
    "CacheMetricsObserver",
    "RequestMetricsMiddleware",
    "metrics_response",
    "instrument_call",
    "SnapshotTelemetryAdapter",
    "snapshot_telemetry",
    "ScenarioTelemetryAdapter",
    "scenario_telemetry",
    "ExtensionTelemetryAdapter",
    "extension_telemetry",
    "HealthTelemetryAdapter",
    "health_telemetry",
]


def _normalise_route(scope: dict[str, Any]) -> str:
    route = scope.get("route")
    if route is None:
        return scope.get("path", "<unrouted>")
    return getattr(route, "path", getattr(route, "name", "<unknown>"))


@dataclass(slots=True)
class MetricsRegistry:
    """Container managing metric families for the application."""

    registry: CollectorRegistry
    request_total: Counter
    request_latency_seconds: Histogram
    request_inflight: Gauge
    cache_hits: Counter
    cache_misses: Counter
    cache_entries: Gauge
    health_checks_total: Counter
    health_check_latency_seconds: Histogram
    health_check_status: Gauge
    snapshot_latency_seconds: Histogram
    snapshot_failures: Counter
    extension_load_total: Counter
    extension_load_latency_seconds: Histogram
    extension_enabled: Gauge
    scenario_runs_total: Counter
    scenario_latency_seconds: Histogram
    scenario_inflight: Gauge

    @classmethod
    def create(cls) -> MetricsRegistry:
        registry = CollectorRegistry()
        request_total = Counter(
            "modacct_http_requests_total",
            "HTTP requests processed by the Modular Accounting API.",
            labelnames=("method", "route", "status"),
            registry=registry,
        )
        request_latency = Histogram(
            "modacct_http_request_latency_seconds",
            "Latency of HTTP requests handled by the API.",
            labelnames=("method", "route"),
            registry=registry,
            buckets=(
                0.005,
                0.01,
                0.025,
                0.05,
                0.1,
                0.25,
                0.5,
                1,
                2.5,
                5,
                10,
            ),
        )
        request_inflight = Gauge(
            "modacct_http_requests_in_flight",
            "Number of in-flight HTTP requests.",
            labelnames=("method", "route"),
            registry=registry,
        )
        cache_hits = Counter(
            "modacct_cache_hits_total",
            "Cache hits recorded by application caches.",
            labelnames=("cache",),
            registry=registry,
        )
        cache_misses = Counter(
            "modacct_cache_misses_total",
            "Cache misses recorded by application caches.",
            labelnames=("cache",),
            registry=registry,
        )
        cache_entries = Gauge(
            "modacct_cache_entries",
            "Current entry count for application caches.",
            labelnames=("cache",),
            registry=registry,
        )
        health_checks_total = Counter(
            "modacct_health_checks_total",
            "Total health check evaluations grouped by outcome.",
            labelnames=("check", "severity", "status"),
            registry=registry,
        )
        health_check_latency = Histogram(
            "modacct_health_check_latency_seconds",
            "Latency of health check evaluations.",
            labelnames=("check", "severity"),
            registry=registry,
            buckets=(
                0.001,
                0.005,
                0.01,
                0.025,
                0.05,
                0.1,
                0.25,
                0.5,
                1,
                2,
            ),
        )
        health_check_status = Gauge(
            "modacct_health_check_status",
            "Gauge reflecting the latest health outcome per check (1=healthy).",
            labelnames=("check", "severity"),
            registry=registry,
        )
        snapshot_latency = Histogram(
            "modacct_snapshot_latency_seconds",
            "Latency to build modular accounting data snapshots.",
            labelnames=("status",),
            registry=registry,
            buckets=(
                0.01,
                0.025,
                0.05,
                0.1,
                0.25,
                0.5,
                1,
                2,
                5,
                10,
            ),
        )
        snapshot_failures = Counter(
            "modacct_snapshot_failures_total",
            "Total snapshot orchestration failures.",
            labelnames=("stage",),
            registry=registry,
        )
        extension_load_total = Counter(
            "modacct_extension_load_total",
            "Total extension load attempts grouped by outcome.",
            labelnames=("module", "status"),
            registry=registry,
        )
        extension_load_latency = Histogram(
            "modacct_extension_load_latency_seconds",
            "Time taken to import and register extension modules.",
            labelnames=("module", "status"),
            registry=registry,
            buckets=(
                0.001,
                0.005,
                0.01,
                0.025,
                0.05,
                0.1,
                0.25,
                0.5,
                1,
                2,
            ),
        )
        extension_enabled = Gauge(
            "modacct_extension_enabled",
            "Flag indicating whether an extension module is enabled and loaded.",
            labelnames=("module",),
            registry=registry,
        )
        scenario_runs_total = Counter(
            "modacct_scenario_runs_total",
            "Total scenario executions grouped by status.",
            labelnames=("scenario", "tags", "status"),
            registry=registry,
        )
        scenario_latency = Histogram(
            "modacct_scenario_latency_seconds",
            "Latency of scenario executions grouped by status.",
            labelnames=("scenario", "tags", "status"),
            registry=registry,
            buckets=(
                0.001,
                0.005,
                0.01,
                0.025,
                0.05,
                0.1,
                0.25,
                0.5,
                1,
                2,
                5,
            ),
        )
        scenario_inflight = Gauge(
            "modacct_scenario_inflight",
            "Number of scenarios currently executing.",
            labelnames=("scenario", "tags"),
            registry=registry,
        )
        return cls(
            registry=registry,
            request_total=request_total,
            request_latency_seconds=request_latency,
            request_inflight=request_inflight,
            cache_hits=cache_hits,
            cache_misses=cache_misses,
            cache_entries=cache_entries,
            health_checks_total=health_checks_total,
            health_check_latency_seconds=health_check_latency,
            health_check_status=health_check_status,
            snapshot_latency_seconds=snapshot_latency,
            snapshot_failures=snapshot_failures,
            extension_load_total=extension_load_total,
            extension_load_latency_seconds=extension_load_latency,
            extension_enabled=extension_enabled,
            scenario_runs_total=scenario_runs_total,
            scenario_latency_seconds=scenario_latency,
            scenario_inflight=scenario_inflight,
        )

    def render_latest(self) -> bytes:
        """Return the Prometheus exposition for the registry."""

        return generate_latest(self.registry)


metrics_registry = MetricsRegistry.create()


class CacheMetricsObserver(CacheObserverProtocol):
    """Adapter bridging :class:`TTLCache` events to Prometheus metrics."""

    def __init__(self, *, registry: MetricsRegistry, cache_name: str) -> None:
        self._registry = registry
        self._cache_name = cache_name

    def record_hit(self) -> None:
        self._registry.cache_hits.labels(cache=self._cache_name).inc()

    def record_miss(self) -> None:
        self._registry.cache_misses.labels(cache=self._cache_name).inc()

    def record_size(self, size: int) -> None:
        self._registry.cache_entries.labels(cache=self._cache_name).set(size)


class SnapshotTelemetryAdapter:
    """Helper exposing higher-level metrics for snapshot orchestration."""

    def __init__(self, registry: MetricsRegistry) -> None:
        self._registry = registry

    def cache_observer(self, cache_name: str) -> CacheMetricsObserver:
        observer = CacheMetricsObserver(registry=self._registry, cache_name=cache_name)
        # Prime the gauge so dashboards show zero rather than missing metrics.
        observer.record_size(0)
        return observer

    def record_latency(self, *, status: str, duration: float) -> None:
        self._registry.snapshot_latency_seconds.labels(status=status).observe(duration)

    def record_failure(self, *, stage: str) -> None:
        self._registry.snapshot_failures.labels(stage=stage).inc()


snapshot_telemetry = SnapshotTelemetryAdapter(metrics_registry)


_logger = logging.getLogger(__name__)


class ExtensionTelemetryAdapter:
    """Helper that records extension lifecycle metrics."""

    def __init__(self, registry: MetricsRegistry) -> None:
        self._registry = registry

    def record_load(self, *, module: str, status: str, duration: float) -> None:
        labels = {"module": module, "status": status}
        try:
            self._registry.extension_load_total.labels(**labels).inc()
            self._registry.extension_load_latency_seconds.labels(**labels).observe(duration)
        except Exception as exc:  # pragma: no cover - defensive
            _logger.debug("Unable to record extension load metrics", exc_info=exc)

    def set_enabled(self, *, module: str, enabled: bool) -> None:
        try:
            self._registry.extension_enabled.labels(module=module).set(1.0 if enabled else 0.0)
        except Exception as exc:  # pragma: no cover - defensive
            _logger.debug("Unable to update extension enabled gauge", exc_info=exc)


extension_telemetry = ExtensionTelemetryAdapter(metrics_registry)


class ScenarioTelemetryAdapter:
    """Helper encapsulating metrics around scenario execution."""

    def __init__(self, registry: MetricsRegistry) -> None:
        self._registry = registry

    @contextmanager
    def track(
        self,
        *,
        scenario: str,
        tags: tuple[str, ...] = (),
    ) -> Iterator[None]:
        """Track metrics for a scenario run within a context manager."""

        label_base = {
            "scenario": scenario,
            "tags": ",".join(sorted(tags)) if tags else "<none>",
        }
        start = time.perf_counter()
        with self._registry.scenario_inflight.labels(**label_base).track_inprogress():
            try:
                yield
            except Exception:
                self._record(status="error", start=start, label_base=label_base)
                raise
            else:
                self._record(status="success", start=start, label_base=label_base)

    @asynccontextmanager
    async def track_async(
        self,
        *,
        scenario: str,
        tags: tuple[str, ...] = (),
    ) -> AsyncIterator[None]:
        """Async counterpart to :meth:`track` for awaitable workloads."""

        label_base = {
            "scenario": scenario,
            "tags": ",".join(sorted(tags)) if tags else "<none>",
        }
        tracker = self._registry.scenario_inflight.labels(**label_base).track_inprogress()
        tracker.__enter__()
        start = time.perf_counter()
        status = "success"
        exc_type: type[BaseException] | None = None
        exc: BaseException | None = None
        tb: TracebackType | None = None
        try:
            yield
        except Exception as err:
            status = "error"
            exc_type = err.__class__
            exc = err
            tb = err.__traceback__
            raise
        finally:
            self._record(status=status, start=start, label_base=label_base)
            tracker.__exit__(exc_type, exc, tb)

    def _record(
        self,
        *,
        status: str,
        start: float,
        label_base: dict[str, str],
    ) -> None:
        duration = time.perf_counter() - start
        labels = {**label_base, "status": status}
        try:
            self._registry.scenario_runs_total.labels(**labels).inc()
            self._registry.scenario_latency_seconds.labels(**labels).observe(duration)
        except Exception as exc:  # pragma: no cover - defensive
            _logger.debug("Unable to update scenario metrics", exc_info=exc)


scenario_telemetry = ScenarioTelemetryAdapter(metrics_registry)


class HealthTelemetryAdapter:
    """Helper emitting metrics around health check execution."""

    def __init__(self, registry: MetricsRegistry) -> None:
        self._registry = registry

    def record_evaluation(
        self,
        *,
        check: str,
        severity: str,
        status: str,
        healthy: bool,
        duration: float,
    ) -> None:
        labels = {"check": check, "severity": severity}
        status_labels = {**labels, "status": status}
        try:
            self._registry.health_checks_total.labels(**status_labels).inc()
            self._registry.health_check_latency_seconds.labels(**labels).observe(duration)
            # Prime gauges so dashboards show an explicit unhealthy value instead of
            # missing series when checks start failing.
            self._registry.health_check_status.labels(**labels).set(1.0 if healthy else 0.0)
        except Exception as exc:  # pragma: no cover - defensive logging only
            _logger.debug("Unable to record health telemetry", exc_info=exc)


health_telemetry = HealthTelemetryAdapter(metrics_registry)


class RequestMetricsMiddleware(BaseHTTPMiddleware):
    """Starlette middleware capturing request level metrics."""

    def __init__(self, app: Any, *, registry: MetricsRegistry) -> None:
        super().__init__(app)
        self._registry = registry

    async def dispatch(  # type: ignore[override]
        self, request: Request, call_next: Callable[[Request], Any]
    ) -> Response:
        route = _normalise_route(request.scope)
        method = request.method
        labels = {"method": method, "route": route}
        start = time.perf_counter()
        with self._registry.request_inflight.labels(**labels).track_inprogress():
            try:
                response = await call_next(request)
                status = response.status_code
            except Exception:
                status = 500
                self._registry.request_total.labels(status=str(status), **labels).inc()
                self._registry.request_latency_seconds.labels(**labels).observe(time.perf_counter() - start)
                raise
        self._registry.request_total.labels(status=str(status), **labels).inc()
        self._registry.request_latency_seconds.labels(**labels).observe(time.perf_counter() - start)
        return response


def metrics_response(registry: MetricsRegistry) -> Response:
    """Return an HTTP response containing metrics in Prometheus format."""

    payload = registry.render_latest()
    return Response(content=payload, media_type=CONTENT_TYPE_LATEST)


@contextmanager
def instrument_call(
    *,
    registry: MetricsRegistry,
    metric: Histogram,
    labels: dict[str, str],
) -> Iterator[None]:
    """Context manager measuring call duration and recording exceptions."""

    start = time.perf_counter()
    try:
        yield
    finally:
        metric.labels(**labels).observe(time.perf_counter() - start)
