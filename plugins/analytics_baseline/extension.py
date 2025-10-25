"""Reference extension that enriches observability metrics."""

from __future__ import annotations

from datetime import UTC, datetime

from apps.extensions import ExtensionManifest, ExtensionRegistry
from apps.observability.health import HealthReport
from apps.observability.metrics import metrics_registry

MANIFEST = ExtensionManifest(
    key="observability:demo",
    name="Baseline Observability",
    version="1.0.0",
    description="Demonstrates extension registration, metrics, and health hooks.",
    capabilities=("analytics", "observability"),
    author="Modular Accounting",
)


def _health_probe() -> HealthReport:
    payload = metrics_registry.render_latest()
    return HealthReport(
        name=f"extension:{MANIFEST.key}",
        healthy=bool(payload),
        severity="info",
        details={
            "metrics_lines": len(payload.splitlines()),
            "checked_at": datetime.now(tz=UTC).isoformat(),
        },
    )


def register(registry: ExtensionRegistry) -> None:
    """Register the baseline analytics extension."""

    registry.register(MANIFEST)
    registry.register_health_check(MANIFEST.key, _health_probe, severity="info")
    # Seed a gauge to advertise the number of declared extension capabilities.
    metrics_registry.cache_entries.labels(cache="extension_capabilities").set(
        float(len(MANIFEST.capabilities))
    )
