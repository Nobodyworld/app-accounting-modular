from __future__ import annotations

from apps.extensions import ExtensionRegistry
from plugins.ops_heartbeat.extension import MANIFEST, register


def test_ops_heartbeat_registers_manifest_and_health() -> None:
    registry = ExtensionRegistry()

    register(registry)

    manifest = registry.get_manifest(MANIFEST.key)
    assert manifest.name == "Operations Heartbeat"

    probe = registry._health_hooks[MANIFEST.key]
    report = probe()
    assert report.healthy
    assert "heartbeat_at" in report.details
