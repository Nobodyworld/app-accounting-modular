"""Health and metrics endpoints for operational visibility."""

from __future__ import annotations

from fastapi import APIRouter

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
