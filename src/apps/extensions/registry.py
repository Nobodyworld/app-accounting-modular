"""Registry primitives for Modular Accounting extensions."""

from __future__ import annotations

import importlib
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import for type checking only
    from apps.observability.health import HealthReport

from apps.observability.metrics import extension_telemetry
from apps.observability.tracing import traced

from .contracts import ExtensionContract

__all__ = [
    "ExtensionManifest",
    "ExtensionRegistry",
    "extension_registry",
    "load_extension_module",
    "load_extensions",
    "ExtensionContract",
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
        self._contracts: dict[str, list[ExtensionContract]] = {}

    def register(self, manifest: ExtensionManifest) -> None:
        """Record extension metadata."""

        self._manifests[manifest.key] = manifest

    def register_contract(self, key: str, contract: ExtensionContract) -> None:
        """Associate a contract with an extension for discovery tooling."""

        bucket = self._contracts.setdefault(key, [])
        bucket.append(contract)

    def register_health_check(self, key: str, hook: HealthHook, *, severity: str = "info") -> None:
        """Expose an extension-defined health check via the global registry."""

        # Local import avoids circular dependency.
        from apps.observability import health as health_module

        def wrapper() -> health_module.HealthReport:
            result = hook()
            if isinstance(result, health_module.HealthReport):
                return result
            return health_module.HealthReport(name=f"extension:{key}", healthy=bool(result), severity=severity)

        health_module.register_health_check(f"extension:{key}", wrapper, severity=severity)
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
        self._contracts.clear()

    def contracts(self) -> dict[str, tuple[ExtensionContract, ...]]:
        """Return registered contracts keyed by extension."""

        return {
            key: tuple(sorted(contracts, key=lambda contract: contract.kind))
            for key, contracts in self._contracts.items()
        }

    def contracts_for(self, key: str) -> tuple[ExtensionContract, ...]:
        """Return contracts registered for ``key``."""

        return tuple(self._contracts.get(key, ()))


extension_registry = ExtensionRegistry()


def load_extension_module(module: str) -> None:
    """Import an extension module and allow it to register itself."""

    start = time.perf_counter()
    status = "success"
    try:
        with traced("extensions.load", module=module):
            try:
                mod = importlib.import_module(module)
                register_fn = getattr(mod, "register", None)
                if callable(register_fn):
                    register_fn(extension_registry)
            except Exception:
                status = "error"
                raise
    finally:
        extension_telemetry.record_load(
            module=module,
            status=status,
            duration=time.perf_counter() - start,
        )


def load_extensions(modules: Iterable[str]) -> list[ExtensionManifest]:
    """Import a collection of extension modules and return their manifests."""

    module_list = list(modules)
    for module in module_list:
        extension_telemetry.set_enabled(module=module, enabled=False)
    for module in module_list:
        try:
            load_extension_module(module)
        except Exception:
            extension_telemetry.set_enabled(module=module, enabled=False)
            raise
        else:
            extension_telemetry.set_enabled(module=module, enabled=True)
    return extension_registry.manifests()
