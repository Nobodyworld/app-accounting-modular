"""Reference extension exposing cashflow instrumentation hooks."""

from __future__ import annotations

from datetime import UTC, datetime

from apps.extensions import ExtensionManifest, ExtensionRegistry
from apps.observability.health import HealthReport
from apps.observability.metrics import metrics_registry
from apps.observability.tracing import traced

MANIFEST = ExtensionManifest(
    key="reporting:cashflow",
    name="Cashflow Analytics",
    version="1.0.0",
    description="Demonstrates extension scaffolding for reporting pipelines.",
    capabilities=("reporting", "cashflow", "analytics"),
    author="Modular Accounting",
)


def _health_probe() -> HealthReport:
    projected_variance = 0.1
    return HealthReport(
        name=f"extension:{MANIFEST.key}",
        healthy=projected_variance < 0.75,
        severity="info",
        details={
            "projected_variance": round(projected_variance, 3),
            "checked_at": datetime.now(tz=UTC).isoformat(),
        },
    )


def register(registry: ExtensionRegistry) -> None:
    """Register the cashflow reporting extension."""

    registry.register(MANIFEST)
    registry.register_health_check(MANIFEST.key, _health_probe, severity="info")

    with traced("cashflow.extension.register", extension_key=MANIFEST.key):
        metrics_registry.cache_entries.labels(cache="cashflow_projection").set(0.0)
