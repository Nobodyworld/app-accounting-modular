"""Telemetry adapters bridging the application layer and observability stack."""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from ..application.cache import CacheObserver

__all__ = ["SnapshotTelemetry", "telemetry_provider"]


class SnapshotTelemetry(Protocol):
    """Interface consumed by :class:`DataSnapshotService` for instrumentation."""

    def cache_observer(self, cache_name: str) -> CacheObserver:
        """Return a cache observer that will record metrics for ``cache_name``."""

    def record_latency(self, *, status: str, duration: float) -> None:
        """Record the time spent building a snapshot with ``status`` outcome."""

    def record_failure(self, *, stage: str) -> None:
        """Increment failure counters for the orchestration ``stage``."""


@lru_cache(maxsize=1)
def telemetry_provider() -> SnapshotTelemetry | None:
    """Return the default snapshot telemetry adapter when available."""

    try:
        from apps.observability.metrics import snapshot_telemetry
    except Exception:  # pragma: no cover - defensive fallback
        return None
    return snapshot_telemetry
