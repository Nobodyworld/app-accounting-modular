"""Core infrastructure routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from apps.observability.health import health_registry

from ..services.plugin_loader import provider_descriptors

router = APIRouter(tags=["core"])


def _provider_snapshot() -> list[dict[str, object]]:
    """Return provider metadata, including compatibility data."""

    return [descriptor.to_dict() for descriptor in provider_descriptors()]


def _provider_compatibility_summary(providers: list[dict[str, object]]) -> dict[str, int]:
    """Summarise compatibility status counts for quick health inspection."""

    counts = {"compatible": 0, "incompatible": 0, "unknown": 0}
    for provider in providers:
        compatibility = provider.get("compatibility") or {}
        status = compatibility.get("status")
        if status in counts:
            counts[status] += 1
        else:  # pragma: no cover - defensive catch-all
            counts["unknown"] += 1
    counts["total"] = len(providers)
    return counts


@router.get("/health")
async def health() -> dict[str, Any]:
    """Return aggregated health information for core subsystems."""

    providers = _provider_snapshot()
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
        "providers": providers,
        "provider_compatibility": _provider_compatibility_summary(providers),
        "checks": checks,
        "database": database,
        "scheduler": scheduler,
    }


@router.get("/providers")
def providers() -> dict[str, list[dict[str, object]]]:
    """List provider plugins exposed via the configuration allowlist."""

    return {"providers": list(_provider_snapshot())}
