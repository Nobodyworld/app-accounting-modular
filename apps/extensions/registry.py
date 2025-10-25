"""Registry primitives for Modular Accounting extensions."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import for type checking only
    from apps.observability.health import HealthReport

__all__ = [
    "ExtensionManifest",
    "ExtensionRegistry",
    "extension_registry",
    "load_extension_module",
    "load_extensions",
]


@dataclass(slots=True, frozen=True)
class ExtensionManifest:
    """Public metadata describing an extension module."""

    key: str
    name: str
    version: str
    description: str | None = None
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    author: str | None = None
    homepage: str | None = None


HealthHook = Callable[[], "HealthReport | bool"]


class ExtensionRegistry:
    """Central registry for tracking installed extensions."""

    def __init__(self) -> None:
        self._manifests: dict[str, ExtensionManifest] = {}
        self._health_hooks: dict[str, HealthHook] = {}

    def register(self, manifest: ExtensionManifest) -> None:
        """Record extension metadata."""

        self._manifests[manifest.key] = manifest

    def register_health_check(
        self, key: str, hook: HealthHook, *, severity: str = "info"
    ) -> None:
        """Expose an extension-defined health check via the global registry."""

        # Local import avoids circular dependency.
        from apps.observability import health as health_module

        def wrapper() -> health_module.HealthReport:
            result = hook()
            if isinstance(result, health_module.HealthReport):
                return result
            return health_module.HealthReport(
                name=f"extension:{key}", healthy=bool(result), severity=severity
            )

        health_module.register_health_check(f"extension:{key}", wrapper)
        self._health_hooks[key] = hook

    def manifests(self) -> list[ExtensionManifest]:
        """Return registered manifests sorted by key."""

        return sorted(self._manifests.values(), key=lambda manifest: manifest.key)

    def get_manifest(self, key: str) -> ExtensionManifest:
        """Return manifest for ``key`` or raise ``KeyError`` if missing."""

        return self._manifests[key]

    def clear(self) -> None:
        """Remove manifests and health hooks (primarily for tests)."""

        self._manifests.clear()
        self._health_hooks.clear()


extension_registry = ExtensionRegistry()


def load_extension_module(module: str) -> None:
    """Import an extension module and allow it to register itself."""

    mod = importlib.import_module(module)
    register_fn = getattr(mod, "register", None)
    if callable(register_fn):
        register_fn(extension_registry)


def load_extensions(modules: Iterable[str]) -> list[ExtensionManifest]:
    """Import a collection of extension modules and return their manifests."""

    for module in modules:
        load_extension_module(module)
    return extension_registry.manifests()
