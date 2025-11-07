"""Plugin discovery and loading helpers."""

from __future__ import annotations

import importlib
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from ..config import ProviderInfo, settings

__all__ = [
    "ProviderHandle",
    "ProviderMetadata",
    "available_providers",
    "load_provider",
    "refresh_provider_cache",
]


@dataclass(frozen=True)
class ProviderMetadata:
    """Publicly exposable metadata describing a provider."""

    key: str
    name: str
    description: str | None
    capabilities: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a serialisable representation of the metadata."""

        return {
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "capabilities": list(self.capabilities),
        }


@dataclass(frozen=True)
class ProviderHandle:
    """A loaded provider instance along with its metadata."""

    instance: Any
    metadata: ProviderMetadata


CapabilitySignature = tuple[str, str, str | None, tuple[str, ...]]


def _provider_signature() -> tuple[CapabilitySignature, ...]:
    """Return a hashable snapshot of allowed providers."""

    snapshot: list[CapabilitySignature] = []
    for key, info in settings.allowed_providers.items():
        snapshot.append(
            (
                key,
                info.module,
                info.description,
                tuple(info.capabilities),
            )
        )
    return tuple(sorted(snapshot))


def _metadata_from_info(key: str, info: ProviderInfo) -> ProviderMetadata:
    return ProviderMetadata(
        key=key,
        name=info.name,
        description=info.description,
        capabilities=tuple(info.capabilities),
    )


@lru_cache(maxsize=32)
def _cached_provider_metadata(
    signature: tuple[CapabilitySignature, ...], capability: str | None
) -> tuple[ProviderMetadata, ...]:
    """Build provider metadata lists keyed by capability filters."""

    metadata: list[ProviderMetadata] = []
    for key, _, _, _capabilities in signature:
        info = settings.allowed_providers.get(key)
        if info is None:
            # Configuration changed after cache key generation; ignore entry.
            continue
        provider_metadata = _metadata_from_info(key, info)
        if capability and capability not in provider_metadata.capabilities:
            continue
        metadata.append(provider_metadata)

    metadata.sort(key=lambda item: item.key)
    return tuple(metadata)


def available_providers(capability: str | None = None) -> list[ProviderMetadata]:
    """Return metadata for providers permitted by configuration."""

    signature = _provider_signature()
    return list(_cached_provider_metadata(signature, capability))


CAPABILITY_METHODS: dict[str, tuple[str, ...]] = {
    "fx": ("sync_daily_rates",),
    "market": ("fetch_prices",),
    "tax": ("upsert_rules",),
}


def _expected_methods(capabilities: Iterable[str]) -> tuple[str, ...]:
    methods: set[str] = set()
    for capability in capabilities:
        methods.update(CAPABILITY_METHODS.get(capability, ()))
    return tuple(sorted(methods))


def _validate_provider_interface(provider: Any, metadata: ProviderMetadata) -> None:
    """Ensure provider instances expose expected attributes for their capabilities."""

    name = getattr(provider, "name", None)
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"Provider '{metadata.key}' must define a non-empty 'name' attribute")

    missing: list[str] = []
    for method_name in _expected_methods(metadata.capabilities):
        attr = getattr(provider, method_name, None)
        if not callable(attr):
            missing.append(method_name)

    if missing:
        methods = ", ".join(sorted(missing))
        raise ValueError(f"Provider '{metadata.key}' is missing required callable methods: {methods}")


def load_provider(key: str, factory: str = "provider") -> ProviderHandle:
    """Load and instantiate an allowed provider referenced by ``key``."""

    if not key:
        raise ValueError("Provider key is required")

    try:
        info = settings.allowed_providers[key]
    except KeyError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Provider '{key}' is not allowed") from exc

    module_path = info.module

    try:
        mod = importlib.import_module(module_path)
    except (ModuleNotFoundError, ImportError) as exc:
        raise ValueError(f"Unable to import provider module '{module_path}' for key '{key}'") from exc

    if not hasattr(mod, factory):
        raise ValueError(f"Factory '{factory}' not found in {module_path}")
    factory_fn = getattr(mod, factory)
    if not callable(factory_fn):  # pragma: no cover - defensive
        raise ValueError(f"Factory '{factory}' in {module_path} is not callable")

    provider = factory_fn()
    if provider is None:
        raise ValueError(f"Factory '{factory}' in {module_path} returned None")

    metadata = _metadata_from_info(key, info)
    _validate_provider_interface(provider, metadata)
    return ProviderHandle(instance=provider, metadata=metadata)


def refresh_provider_cache() -> None:
    """Invalidate cached provider metadata snapshots."""

    _cached_provider_metadata.cache_clear()
