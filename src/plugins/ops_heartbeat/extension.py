"""Operational heartbeat extension that emits telemetry for observability."""

from __future__ import annotations

from datetime import UTC, datetime

from apps.extensions import ExtensionManifest, ExtensionRegistry
from apps.observability.health import HealthReport
from apps.observability.metrics import Gauge, metrics_registry

MANIFEST = ExtensionManifest(
    key="ops:heartbeat",
    name="Operations Heartbeat",
    version="0.1.0",
    description="Publishes a heartbeat gauge that downstream monitors can scrape.",
    capabilities=("operations", "monitoring"),
    author="Modular Accounting",
)

_HEARTBEAT_GAUGE = Gauge(
    "modacct_ops_heartbeat_timestamp",
    "Unix timestamp of the most recent heartbeat emitted by the ops extension.",
    labelnames=(),
    registry=metrics_registry.registry,
)
_HEARTBEAT_HANDLE = _HEARTBEAT_GAUGE.labels()
_HEARTBEAT_HANDLE.set(0.0)


def _heartbeat_probe() -> HealthReport:
    moment = datetime.now(tz=UTC)
    _HEARTBEAT_HANDLE.set(moment.timestamp())
    return HealthReport(
        name=f"extension:{MANIFEST.key}",
        healthy=True,
        severity="info",
        details={"heartbeat_at": moment.isoformat()},
    )


def register(registry: ExtensionRegistry) -> None:
    """Register the heartbeat extension."""

    registry.register(MANIFEST)
    registry.register_health_check(MANIFEST.key, _heartbeat_probe, severity="info")
