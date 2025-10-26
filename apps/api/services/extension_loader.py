"""Helpers for loading and enumerating optional extensions."""

from __future__ import annotations

from dataclasses import dataclass

from apps.extensions import ExtensionManifest, extension_registry, load_extensions
from apps.observability.metrics import extension_telemetry

from ..config import ExtensionInfo, settings

__all__ = ["ExtensionStatus", "active_extensions", "load_configured_extensions"]


@dataclass(slots=True, frozen=True)
class ExtensionStatus:
    """Materialised view of configured extension state."""

    key: str
    module: str
    manifest: ExtensionManifest | None
    enabled: bool


def _enabled_modules(configured: dict[str, ExtensionInfo]) -> list[str]:
    modules: list[str] = []
    for info in configured.values():
        if info.enabled:
            modules.append(info.module)
    return modules


def load_configured_extensions() -> list[ExtensionManifest]:
    """Load enabled extensions based on configuration."""

    extension_registry.clear()
    for info in settings.allowed_extensions.values():
        extension_telemetry.set_enabled(module=info.module, enabled=False)
    modules = _enabled_modules(settings.allowed_extensions)
    return load_extensions(modules)


def active_extensions() -> list[ExtensionStatus]:
    """Return configured extensions along with activation state."""

    manifests = {manifest.key: manifest for manifest in extension_registry.manifests()}
    status: list[ExtensionStatus] = []
    for key, info in settings.allowed_extensions.items():
        manifest = manifests.get(key)
        status.append(
            ExtensionStatus(
                key=key,
                module=info.module,
                manifest=manifest,
                enabled=info.enabled,
            )
        )
    status.sort(key=lambda item: item.key)
    return status
