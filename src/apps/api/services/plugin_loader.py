"""Plugin discovery and loading helpers."""

from __future__ import annotations

import importlib
import inspect
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

from apps.api.version import API_VERSION
from ..config import ProviderInfo, settings

__all__ = [
    "ProviderHandle",
    "ProviderMetadata",
    "ProviderCompatibility",
    "ProviderDescriptor",
    "available_providers",
    "load_provider",
    "refresh_provider_cache",
    "provider_descriptors",
]

logger = logging.getLogger(__name__)


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


@dataclass(frozen=True)
class ProviderCompatibility:
    """Compatibility status between a provider and the API."""

    api_version: str
    provider_version: str | None
    status: Literal["compatible", "incompatible", "unknown"]
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "api_version": self.api_version,
            "provider_version": self.provider_version,
            "status": self.status,
        }
        if self.reason:
            payload["reason"] = self.reason
        return payload


@dataclass(frozen=True)
class ProviderDescriptor:
    """Extended view of provider metadata used in public endpoints."""

    metadata: ProviderMetadata
    module: str
    version: str | None
    compatibility: ProviderCompatibility

    def to_dict(self) -> dict[str, object]:
        """Return a serialisable representation including compatibility data."""

        payload = self.metadata.to_dict()
        payload.update(
            {
                "module": self.module,
                "version": self.version,
                "compatibility": self.compatibility.to_dict(),
            }
        )
        return payload


CapabilitySignature = tuple[str, str, str | None, tuple[str, ...]]
_VERSION_PATTERN = re.compile(r"^(?P<major>\d+)")


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


def _provider_version(module_path: str) -> str | None:
    """Extract a declared provider version if available."""

    try:
        module = importlib.import_module(module_path)
    except Exception as exc:  # pragma: no cover - defensive log path
        logger.debug(
            "Unable to import provider module for version detection",
            extra={"module": module_path, "error": str(exc)},
        )
        return None

    for attr in ("__version__", "VERSION", "version"):
        value = getattr(module, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _major(version: str | None) -> int | None:
    if not version:
        return None
    match = _VERSION_PATTERN.match(version)
    if match is None:
        return None
    try:
        return int(match.group("major"))
    except ValueError:
        return None


def _compatibility(provider_version: str | None) -> ProviderCompatibility:
    api_major = _major(API_VERSION)
    provider_major = _major(provider_version)

    if api_major is None:
        return ProviderCompatibility(
            api_version=API_VERSION,
            provider_version=provider_version,
            status="unknown",
            reason="api version is not parseable",
        )
    if provider_major is None:
        return ProviderCompatibility(
            api_version=API_VERSION,
            provider_version=provider_version,
            status="unknown",
            reason="provider version is not declared or parseable",
        )
    if provider_major != api_major:
        return ProviderCompatibility(
            api_version=API_VERSION,
            provider_version=provider_version,
            status="incompatible",
            reason=f"provider major {provider_major} differs from api major {api_major}",
        )
    return ProviderCompatibility(
        api_version=API_VERSION,
        provider_version=provider_version,
        status="compatible",
    )


@lru_cache(maxsize=32)
def _cached_provider_descriptors(
    signature: tuple[CapabilitySignature, ...],
    capability: str | None,
) -> tuple[ProviderDescriptor, ...]:
    """Build provider descriptors, caching the expensive version lookups."""

    descriptors: list[ProviderDescriptor] = []
    for key, module, _, _capabilities in signature:
        info = settings.allowed_providers.get(key)
        if info is None:
            continue
        metadata = _metadata_from_info(key, info)
        if capability and capability not in metadata.capabilities:
            continue
        version = _provider_version(module)
        descriptors.append(
            ProviderDescriptor(
                metadata=metadata,
                module=module,
                version=version,
                compatibility=_compatibility(version),
            )
        )

    descriptors.sort(key=lambda item: item.metadata.key)

    incompatible = [
        descriptor
        for descriptor in descriptors
        if descriptor.compatibility.status == "incompatible"
    ]
    if incompatible:
        logger.warning(
            "Incompatible providers detected",
            extra={
                "providers": [
                    {
                        "key": d.metadata.key,
                        "module": d.module,
                        "provider_version": d.version,
                        "reason": d.compatibility.reason,
                    }
                    for d in incompatible
                ]
            },
        )

    return tuple(descriptors)


def provider_descriptors(capability: str | None = None) -> list[ProviderDescriptor]:
    """Return provider descriptors including compatibility summaries."""

    signature = _provider_signature()
    return list(_cached_provider_descriptors(signature, capability))


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
    if inspect.iscoroutine(provider):  # type: ignore[arg-type]
        try:
            provider.close()  # type: ignore[call-arg]
        except Exception:
            pass
        raise ValueError("Async provider factories are not supported; use synchronous factories")
    if provider is None:
        raise ValueError(f"Factory '{factory}' in {module_path} returned None")

    metadata = _metadata_from_info(key, info)
    _validate_provider_interface(provider, metadata)
    return ProviderHandle(instance=provider, metadata=metadata)


def refresh_provider_cache() -> None:
    """Invalidate cached provider metadata snapshots."""

    _cached_provider_metadata.cache_clear()
    _cached_provider_descriptors.cache_clear()
