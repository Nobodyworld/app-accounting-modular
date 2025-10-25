"""Health check registry and evaluation utilities."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

__all__ = [
    "HealthReport",
    "HealthRegistry",
    "health_registry",
    "register_health_check",
]


@dataclass(slots=True)
class HealthReport:
    """Outcome of a health probe executed against a subsystem."""

    name: str
    healthy: bool
    details: dict[str, Any] = field(default_factory=dict)
    severity: str = "critical"


HealthCheck = Callable[[], Awaitable[HealthReport] | HealthReport]


class HealthRegistry:
    """Container orchestrating health check execution and aggregation."""

    def __init__(self) -> None:
        self._checks: dict[str, HealthCheck] = {}

    def register(self, name: str, check: HealthCheck) -> None:
        """Register a named health check. Later registrations override."""

        self._checks[name] = check

    def unregister(self, name: str) -> None:
        """Remove a health check from the registry when no longer needed."""

        self._checks.pop(name, None)

    async def evaluate(self) -> list[HealthReport]:
        """Execute all registered checks and return their reports."""

        reports: list[HealthReport] = []
        for name, check in self._checks.items():
            result = check()
            if inspect.isawaitable(result):
                report = await asyncio.wait_for(result, timeout=5)
            else:
                report = result
            if not isinstance(report, HealthReport):
                report = HealthReport(name=name, healthy=bool(report))
            elif report.name != name:
                report = HealthReport(
                    name=name,
                    healthy=report.healthy,
                    details=report.details,
                    severity=report.severity,
                )
            reports.append(report)
        return reports

    async def evaluate_by_severity(self) -> dict[str, list[HealthReport]]:
        """Return reports keyed by severity to simplify incident handling."""

        reports = await self.evaluate()
        buckets: dict[str, list[HealthReport]] = {}
        for report in reports:
            buckets.setdefault(report.severity, []).append(report)
        return buckets

    def list_checks(self) -> list[str]:
        """Return registered check names for diagnostics and tooling."""

        return sorted(self._checks)


health_registry = HealthRegistry()


def register_health_check(name: str, check: HealthCheck) -> None:
    """Module level helper delegating to :class:`HealthRegistry`."""

    health_registry.register(name, check)
