"""Core infrastructure routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from apps.observability.health import health_registry

from ..services.plugin_loader import provider_descriptors

router = APIRouter(tags=["core"])


def _provider_snapshot() -> list[dict[str, Any]]:
    """Return provider metadata, including compatibility data."""

    return [descriptor.to_dict() for descriptor in provider_descriptors()]


def _provider_compatibility_summary(providers: list[dict[str, Any]]) -> dict[str, int]:
    """Summarise compatibility status counts for quick health inspection."""

    counts = {"compatible": 0, "incompatible": 0, "unknown": 0}
    known_statuses = frozenset(counts)
    for provider in providers:
        # provider dicts may contain arbitrary values; treat as Mapping-like
        compatibility = provider.get("compatibility") if isinstance(provider, dict) else None
        compatibility = compatibility or {}
        status = compatibility.get("status") if isinstance(compatibility, dict) else None
        bucket = str(status) if str(status) in known_statuses else "unknown"
        counts[bucket] += 1
    counts["total"] = len(providers)
    return counts


def _provider_compatibility_alerts(providers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a list of provider compatibility alerts for surfaced diagnostics."""

    alerts: list[dict[str, Any]] = []
    for provider in providers:
        compatibility = provider.get("compatibility")
        if not isinstance(compatibility, dict):
            continue
        status = compatibility.get("status")
        if status == "incompatible":
            alerts.append(
                {
                    "provider": provider.get("key") or provider.get("name"),
                    "status": status,
                    "reason": compatibility.get("reason"),
                    "provider_version": compatibility.get("provider_version"),
                    "api_version": compatibility.get("api_version"),
                }
            )
    return alerts


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
        "provider_alerts": _provider_compatibility_alerts(providers),
        "checks": checks,
        "database": database,
        "scheduler": scheduler,
    }


@router.get("/providers")
def providers() -> dict[str, list[dict[str, object]]]:
    """List provider plugins exposed via the configuration allowlist."""

    return {"providers": list(_provider_snapshot())}
