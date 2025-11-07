"""Operations resilience extension exposing an incident playbook contract."""

from __future__ import annotations

from datetime import UTC, datetime

from apps.extensions import ExtensionManifest, ExtensionRegistry
from apps.extensions.contracts import ExtensionContract
from apps.observability.health import HealthReport

MANIFEST = ExtensionManifest(
    key="ops:resilience",
    name="Operations Resilience",
    version="0.1.0",
    description="Ships incident playbooks and health probes for operators.",
    capabilities=("operations", "observability"),
    author="Modular Accounting",
)

_INCIDENT_PLAYBOOK: tuple[dict[str, str], ...] = (
    {
        "step": "database",
        "action": "Verify database connectivity, credentials, and pending migrations.",
    },
    {
        "step": "metrics",
        "action": "Confirm Prometheus scrapes succeed and restart the exporter if stale.",
    },
    {
        "step": "tracing",
        "action": "Check OTLP endpoints and ensure the tracing pipeline is configured.",
    },
)

PLAYBOOK_CONTRACT = ExtensionContract(
    kind="observability:incident-playbook",
    name="Operations Incident Playbook",
    version="1.0",
    description="Provides a baseline incident response playbook for observability checks.",
    entrypoint="plugins.ops_resilience.extension:get_playbook",
    tags=("observability", "operations", "playbook"),
)


def get_playbook() -> list[dict[str, str]]:
    """Return a serialisable copy of the incident playbook steps."""

    return [dict(step=item["step"], action=item["action"]) for item in _INCIDENT_PLAYBOOK]


def _resilience_probe() -> HealthReport:
    """Emit a health report summarising the state of the playbook."""

    generated = datetime.now(tz=UTC)
    return HealthReport(
        name=f"extension:{MANIFEST.key}",
        healthy=True,
        severity="info",
        details={
            "playbook_steps": len(_INCIDENT_PLAYBOOK),
            "generated_at": generated.isoformat(),
        },
    )


def register(registry: ExtensionRegistry) -> None:
    """Register the operations resilience extension."""

    registry.register(MANIFEST)
    registry.register_contract(MANIFEST.key, PLAYBOOK_CONTRACT)
    registry.register_health_check(MANIFEST.key, _resilience_probe, severity="info")
