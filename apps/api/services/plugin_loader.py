"""Plugin discovery and loading helpers."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

from ..config import ProviderInfo, settings

__all__ = [
    "ProviderHandle",
    "ProviderMetadata",
    "available_providers",
    "load_provider",
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


def _metadata_from_info(key: str, info: ProviderInfo) -> ProviderMetadata:
    return ProviderMetadata(
        key=key,
        name=info.name,
        description=info.description,
        capabilities=tuple(info.capabilities),
    )


def available_providers(capability: str | None = None) -> list[ProviderMetadata]:
    """Return metadata for providers permitted by configuration."""

    providers: list[ProviderMetadata] = []
    for key, info in settings.allowed_providers.items():
        metadata = _metadata_from_info(key, info)
        if capability and capability not in metadata.capabilities:
            continue
        providers.append(metadata)
    providers.sort(key=lambda item: item.key)
    # TODO - Cache provider metadata to avoid rebuilding the list per request.
    return providers


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
        raise ValueError(
            f"Unable to import provider module '{module_path}' for key '{key}'"
        ) from exc

    if not hasattr(mod, factory):
        raise ValueError(f"Factory '{factory}' not found in {module_path}")
    factory_fn = getattr(mod, factory)
    if not callable(factory_fn):  # pragma: no cover - defensive
        raise ValueError(f"Factory '{factory}' in {module_path} is not callable")

    provider = factory_fn()
    if provider is None:
        raise ValueError(f"Factory '{factory}' in {module_path} returned None")

    # TODO - Validate provider interface compliance before exposing the handle.
    return ProviderHandle(instance=provider, metadata=_metadata_from_info(key, info))
