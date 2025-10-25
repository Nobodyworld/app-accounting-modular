"""Prometheus-compatible metrics primitives and FastAPI middleware."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

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
                labels = ",".join(
                    f'{name}="{val}"'
                    for name, val in zip(metric._labelnames, key, strict=False)
                    if name
                )
                label_str = f"{{{labels}}}" if labels else ""
                lines.append(f"{metric.name}{label_str} {value}")
        return ("\n".join(lines) + "\n").encode()
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from apps.modular_accounting.application.cache import CacheObserver

__all__ = [
    "MetricsRegistry",
    "metrics_registry",
    "CacheMetricsObserver",
    "RequestMetricsMiddleware",
    "metrics_response",
    "instrument_call",
    "SnapshotTelemetryAdapter",
    "snapshot_telemetry",
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
    snapshot_latency_seconds: Histogram
    snapshot_failures: Counter

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
        return cls(
            registry=registry,
            request_total=request_total,
            request_latency_seconds=request_latency,
            request_inflight=request_inflight,
            cache_hits=cache_hits,
            cache_misses=cache_misses,
            cache_entries=cache_entries,
            snapshot_latency_seconds=snapshot_latency,
            snapshot_failures=snapshot_failures,
        )

    def render_latest(self) -> bytes:
        """Return the Prometheus exposition for the registry."""

        return generate_latest(self.registry)


metrics_registry = MetricsRegistry.create()


class CacheMetricsObserver(CacheObserver):
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
                self._registry.request_latency_seconds.labels(**labels).observe(
                    time.perf_counter() - start
                )
                raise
        self._registry.request_total.labels(status=str(status), **labels).inc()
        self._registry.request_latency_seconds.labels(**labels).observe(
            time.perf_counter() - start
        )
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
