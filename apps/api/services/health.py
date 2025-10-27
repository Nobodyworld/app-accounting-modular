"""Service-layer health checks for the Modular Accounting API."""
from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from ..db import engine
from ..scheduler import get_scheduler_state
from .extension_loader import active_extensions

__all__ = ["register_default_health_checks"]


if TYPE_CHECKING:  # pragma: no cover - type hints only
    from apps.observability.health import HealthReport
else:  # pragma: no cover - runtime placeholder
    HealthReport = Any


def _report(
    *,
    name: str,
    healthy: bool,
    severity: str = "critical",
    details: dict[str, object] | None = None,
) -> HealthReport:
    from apps.observability.health import HealthReport

    return HealthReport(
        name=name,
        healthy=healthy,
        severity=severity,
        details=details or {},
    )


def _database_health() -> HealthReport:
    with suppress(Exception):
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            return _report(name="database", healthy=True)
    return _report(
        name="database",
        healthy=False,
        details={"error": "Database connectivity check failed"},
    )


def _metrics_health() -> HealthReport:
    from apps.observability.metrics import metrics_registry

    try:
        payload = metrics_registry.render_latest()
    except Exception as exc:  # pragma: no cover - defensive
        return _report(
            name="metrics",
            healthy=False,
            severity="warning",
            details={"error": str(exc)},
        )
    return _report(
        name="metrics",
        healthy=bool(payload),
        severity="info",
        details={"registry_metrics": len(payload.splitlines())},
    )


def _scheduler_health() -> HealthReport:
    state = get_scheduler_state()
    healthy = state.get("running", False)
    severity = "info" if healthy else "warning"
    return _report(
        name="scheduler",
        healthy=healthy,
        severity=severity,
        details=state,
    )


def _tracing_health() -> HealthReport:
    from apps.observability.tracing import get_tracing_config, is_tracing_enabled

    config = get_tracing_config()
    healthy = is_tracing_enabled()
    severity = "info" if healthy else "warning"
    details: dict[str, object] = {
        "exporter": config.exporter if config else "disabled",
        "otel_enabled": bool(config and config.otel_enabled),
    }
    if config and config.endpoint:
        details["endpoint"] = config.endpoint
    return _report(
        name="tracing",
        healthy=healthy,
        severity=severity,
        details=details,
    )


def _extensions_health() -> HealthReport:
    statuses = active_extensions()
    enabled = [status for status in statuses if status.enabled]
    missing = [status for status in enabled if status.manifest is None]
    severity = "warning" if missing else "info"
    details = {
        "configured": len(statuses),
        "enabled": len(enabled),
        "loaded": [status.key for status in enabled if status.manifest is not None],
        "missing": [status.key for status in missing],
    }
    return _report(
        name="extensions",
        healthy=not missing,
        severity=severity,
        details=details,
    )


def register_default_health_checks() -> None:
    """Install the built-in health checks for API bootstrapping."""
    from apps.observability.health import register_health_check

    register_health_check("database", _database_health, severity="critical")
    register_health_check("metrics", _metrics_health, severity="warning")
    register_health_check("scheduler", _scheduler_health, severity="warning")
    register_health_check("tracing", _tracing_health, severity="info")
    register_health_check("extensions", _extensions_health, severity="info")
