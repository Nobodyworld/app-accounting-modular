"""Health registry primitives for modular accounting observability."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

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


HealthCheck = Callable[[], Awaitable[HealthReport | bool] | HealthReport | bool]


class HealthRegistry:
    """Container orchestrating health check execution and aggregation."""

    def __init__(self) -> None:
        self._checks: dict[str, HealthCheck] = {}
        self._metadata: dict[str, dict[str, str]] = {}

    def register(
        self,
        name: str,
        check: HealthCheck,
        *,
        severity: str = "critical",
    ) -> None:
        """Register a named health check. Later registrations override."""

        self._checks[name] = check
        self._metadata[name] = {"severity": severity}

    def unregister(self, name: str) -> None:
        """Remove a health check from the registry when no longer needed."""

        self._checks.pop(name, None)
        self._metadata.pop(name, None)

    async def evaluate(self) -> list[HealthReport]:
        """Execute all registered checks and return their reports."""

        reports: list[HealthReport] = []
        # Import at runtime to avoid module cycles during process startup.
        from apps.observability.metrics import health_telemetry

        for name, check in self._checks.items():
            metadata = self._metadata.get(name, {})
            severity_hint = metadata.get("severity", "critical")
            status = "completed"
            start = time.perf_counter()
            try:
                result = check()
                if inspect.isawaitable(result):
                    result = await asyncio.wait_for(result, timeout=5)
                if isinstance(result, HealthReport):
                    report = result
                else:
                    report = HealthReport(
                        name=name,
                        healthy=bool(result),
                        severity=severity_hint,
                    )
            except Exception as exc:  # pragma: no cover - defensive safety net
                status = "exception"
                report = HealthReport(
                    name=name,
                    healthy=False,
                    severity=severity_hint,
                    details={"error": str(exc)},
                )
            else:
                if report.name != name:
                    report = HealthReport(
                        name=name,
                        healthy=report.healthy,
                        details=report.details,
                        severity=report.severity,
                    )
            finally:
                duration = time.perf_counter() - start
                health_telemetry.record_evaluation(
                    check=name,
                    severity=report.severity,
                    status=status,
                    healthy=report.healthy,
                    duration=duration,
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


def register_health_check(name: str, check: HealthCheck, *, severity: str = "critical") -> None:
    """Module level helper delegating to :class:`HealthRegistry`."""

    health_registry.register(name, check, severity=severity)
