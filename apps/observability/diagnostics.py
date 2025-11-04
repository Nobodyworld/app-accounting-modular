"""Observability snapshot helpers and incident guidance utilities."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from apps.observability.health import HealthReport, health_registry
from apps.observability.metrics import metrics_registry
from apps.observability.tracing import get_tracing_config, is_tracing_enabled

__all__ = [
    "ObservabilitySnapshot",
    "collect_observability_snapshot",
]

_INCIDENT_PLAYBOOK: dict[str, str] = {
    "database": "Verify the database service is reachable and apply pending migrations.",
    "metrics": "Restart the API process or exporter responsible for Prometheus scraping.",
    "scheduler": "Inspect the scheduler logs and ensure the background worker is running.",
    "tracing": "Confirm the tracing exporter configuration and OTLP endpoint reachability.",
    "extensions": "Reload configured extensions and review recent extension load failures.",
}
_DEFAULT_INCIDENT_ACTION = "Consult the operations runbook for recovery steps and escalate if unresolved."


@dataclass(slots=True)
class ObservabilitySnapshot:
    """Aggregated view of metrics, health reports, tracing, and extensions."""

    generated_at: str
    metrics: dict[str, Any]
    health: dict[str, Any]
    incidents: list[dict[str, Any]]
    tracing: dict[str, Any]
    extensions: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation of the snapshot."""

        return {
            "generated_at": self.generated_at,
            "metrics": self.metrics,
            "health": self.health,
            "incidents": self.incidents,
            "tracing": self.tracing,
            "extensions": self.extensions,
        }


def _serialise_report(report: HealthReport) -> dict[str, Any]:
    return {
        "name": report.name,
        "healthy": report.healthy,
        "severity": report.severity,
        "details": report.details,
    }


def _aggregate_health(reports: Iterable[HealthReport]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    grouped: dict[str, dict[str, int]] = {}
    incidents: list[dict[str, Any]] = []
    for report in reports:
        bucket = grouped.setdefault(report.severity, {"total": 0, "open": 0})
        bucket["total"] += 1
        if not report.healthy:
            bucket["open"] += 1
            incidents.append(
                {
                    "name": report.name,
                    "severity": report.severity,
                    "details": report.details,
                    "action": _INCIDENT_PLAYBOOK.get(report.name.split(":", 1)[-1], _DEFAULT_INCIDENT_ACTION),
                }
            )
    return {severity: stats for severity, stats in sorted(grouped.items())}, incidents


async def collect_observability_snapshot(
    *,
    extension_status_provider: Callable[[], Iterable[Any]] | None = None,
) -> ObservabilitySnapshot:
    """Evaluate health checks and return a consolidated observability snapshot."""

    reports = await health_registry.evaluate()
    metrics_payload = metrics_registry.render_latest()
    metrics_lines = [line for line in metrics_payload.decode().splitlines() if line.strip()]
    health_reports = [_serialise_report(report) for report in reports]
    health_summary, incidents = _aggregate_health(reports)

    tracing_config = get_tracing_config()
    tracing_summary: dict[str, Any] = {
        "enabled": is_tracing_enabled(),
        "exporter": tracing_config.exporter if tracing_config else "disabled",
        "otel_enabled": bool(tracing_config and tracing_config.otel_enabled),
    }
    if tracing_config and tracing_config.endpoint:
        tracing_summary["endpoint"] = tracing_config.endpoint

    extensions: list[dict[str, Any]] = []
    if extension_status_provider is not None:
        for status in extension_status_provider():
            manifest = getattr(status, "manifest", None)
            extensions.append(
                {
                    "key": getattr(status, "key", "<unknown>"),
                    "module": getattr(status, "module", "<unknown>"),
                    "enabled": bool(getattr(status, "enabled", False)),
                    "loaded": manifest is not None,
                    "capabilities": list(getattr(manifest, "capabilities", ())),
                }
            )

    snapshot = ObservabilitySnapshot(
        generated_at=datetime.now(tz=UTC).isoformat(),
        metrics={
            "lines": len(metrics_lines),
            "bytes": len(metrics_payload),
            "checks": health_registry.list_checks(),
        },
        health={
            "reports": health_reports,
            "by_severity": health_summary,
        },
        incidents=incidents,
        tracing=tracing_summary,
        extensions=extensions,
    )
    return snapshot
