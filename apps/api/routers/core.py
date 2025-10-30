"""Core infrastructure routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from apps.observability.health import health_registry

from ..services.plugin_loader import available_providers

router = APIRouter(tags=["core"])


@router.get("/health")
async def health() -> dict[str, Any]:
    """Return aggregated health information for core subsystems."""

    reports = await health_registry.evaluate()
    checks: list[dict[str, Any]] = [
        {
            "name": report.name,
            "healthy": report.healthy,
            "severity": report.severity,
            "details": dict(report.details or {}),
        }
        for report in reports
    ]
    checks_by_name = {entry["name"]: entry for entry in checks}

    def _ensure_check(name: str, *, severity: str) -> dict[str, Any]:
        check = checks_by_name.get(name)
        if check is None:
            check = {
                "name": name,
                "healthy": None,
                "severity": severity,
                "details": {"error": "health check not registered"},
            }
            checks.append(check)
            checks_by_name[name] = check
        return check

    database = _ensure_check("database", severity="critical")
    scheduler = _ensure_check("scheduler", severity="warning")

    def _determine_status(entries: list[dict[str, Any]]) -> str:
        if not entries:
            return "unknown"
        has_warning = False
        has_success = False
        for entry in entries:
            healthy = entry.get("healthy")
            if healthy is True:
                has_success = True
            elif healthy is False:
                if entry.get("severity") == "critical":
                    return "critical"
                has_warning = True
        if has_warning:
            return "degraded"
        return "ok" if has_success else "unknown"

    status = _determine_status(checks)

    return {
        "status": status,
        "checks": checks,
        "database": database,
        "scheduler": scheduler,
    }


@router.get("/providers")
def providers() -> dict[str, list[dict[str, object]]]:
    """List provider plugins exposed via the configuration allowlist."""

    # TODO - Cache provider metadata and include version compatibility info.
    return {"providers": [meta.to_dict() for meta in available_providers()]}
