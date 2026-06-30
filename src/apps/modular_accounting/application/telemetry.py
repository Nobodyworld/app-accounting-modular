"""Telemetry adapters bridging the application layer and observability stack."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Protocol

from .cache import CacheObserver

__all__ = ["SnapshotTelemetry", "telemetry_provider"]


class SnapshotTelemetry(Protocol):
    """Interface consumed by :class:`DataSnapshotService` for instrumentation."""

    def cache_observer(self, cache_name: str) -> CacheObserver:
        """Return a cache observer that records metrics for ``cache_name``."""

    def record_latency(self, *, status: str, duration: float) -> None:
        """Record the time spent building a snapshot with ``status`` outcome."""

    def record_failure(self, *, stage: str) -> None:
        """Increment failure counters for the orchestration ``stage``."""


_logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def telemetry_provider() -> SnapshotTelemetry | None:
    """Return the default snapshot telemetry adapter when available.

    The observability subsystem is an optional dependency.  Import errors are
    swallowed so the application layer can operate in environments where the
    metrics package is excluded (for example, minimal CLI distributions).
    """

    try:
        from apps.observability.metrics import snapshot_telemetry
    except ModuleNotFoundError:
        _logger.debug(
            "Observability metrics package not available; snapshot telemetry disabled.",
        )
        return None
    except ImportError as exc:
        _logger.warning(
            "Observability metrics module missing snapshot telemetry adapter; disabling instrumentation.",
            exc_info=exc,
        )
        return None

    return snapshot_telemetry
