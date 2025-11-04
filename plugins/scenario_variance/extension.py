"""Scenario variance extension advertising augmentation contracts."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from apps.extensions import (
    ExtensionContract,
    ExtensionManifest,
    ExtensionRegistry,
)
from apps.modular_accounting.application import SnapshotScenario
from apps.observability.health import HealthReport

MANIFEST = ExtensionManifest(
    key="scenarios:variance",
    name="Scenario Variance Toolkit",
    version="1.0.0",
    description="Supplies reference variance contracts for scenario stress testing.",
    capabilities=("scenarios", "analysis", "automation"),
    author="Modular Accounting",
)

VARIANCE_CONTRACT = ExtensionContract(
    kind="scenario-augmentation",
    name="Base currency variance",
    version="1.0.0",
    description="Generates +/-5% stress variants for snapshot scenarios.",
    entrypoint="plugins.scenario_variance.extension:generate_variants",
    input_schema={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["name"],
    },
    output_schema={
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["name", "tags"],
        },
    },
    tags=("stress", "fx", "variance"),
)


def _health_probe() -> HealthReport:
    return HealthReport(
        name=f"extension:{MANIFEST.key}",
        healthy=True,
        severity="info",
        details={
            "contracts": 1,
            "checked_at": datetime.now(tz=UTC).isoformat(),
        },
    )


def generate_variants(scenario: SnapshotScenario) -> Iterable[SnapshotScenario]:
    """Yield stress-test variants derived from ``scenario``."""

    base_tags = tuple(scenario.tags)
    suffixes = {"downside": -5, "upside": 5}
    for label, percentage in suffixes.items():
        yield SnapshotScenario(
            name=f"{scenario.name}_{label}",
            request=scenario.request,
            tags=base_tags + (f"variance:{label}", f"shift:{percentage}"),
        )


def register(registry: ExtensionRegistry) -> None:
    """Register the scenario variance extension."""

    registry.register(MANIFEST)
    registry.register_contract(MANIFEST.key, VARIANCE_CONTRACT)
    registry.register_health_check(MANIFEST.key, _health_probe, severity="info")
