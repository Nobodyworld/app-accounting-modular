"""Health, telemetry, and metrics endpoints for the public API."""
from __future__ import annotations

from fastapi import APIRouter

from apps.api.services.extension_loader import active_extensions
from apps.observability.health import health_registry
from apps.observability.metrics import metrics_registry, metrics_response

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/live", summary="Liveness probe")
async def live() -> dict[str, str]:
    """Return OK when the process is reachable."""

    return {"status": "ok"}


@router.get("/ready", summary="Readiness probe")
async def ready() -> dict[str, object]:
    """Execute registered health checks and return their status."""

    reports = await health_registry.evaluate()
    critical_failures = [
        report
        for report in reports
        if not report.healthy and report.severity == "critical"
    ]
    status = "ok" if not critical_failures else "degraded"
    return {
        "status": status,
        "reports": [
            {
                "name": report.name,
                "healthy": report.healthy,
                "severity": report.severity,
                "details": report.details,
            }
            for report in reports
        ],
    }


@router.get("/metrics", summary="Prometheus metrics")
def metrics():
    """Expose metrics in Prometheus text format."""

    return metrics_response(metrics_registry)


@router.get("/telemetry", summary="Aggregated telemetry summary")
async def telemetry() -> dict[str, object]:
    """Return a consolidated snapshot of metrics, health probes, and extensions."""

    reports = await health_registry.evaluate()
    metrics_payload = metrics_registry.render_latest().decode()
    extensions = [
        {
            "key": status.key,
            "module": status.module,
            "enabled": status.enabled,
            "loaded": status.manifest is not None,
        }
        for status in active_extensions()
    ]
    return {
        "metrics": {
            "lines": len([line for line in metrics_payload.splitlines() if line.strip()]),
        },
        "health": [
            {
                "name": report.name,
                "healthy": report.healthy,
                "severity": report.severity,
            }
            for report in reports
        ],
        "extensions": extensions,
    }
