"""Provider discovery and fail-closed loading helpers."""

from __future__ import annotations

import importlib
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

from apps.api.version import API_VERSION
from apps.provider_sdk import (
    ProviderConformanceError,
    ProviderConformanceReport,
    ProviderManifest,
    inspect_provider_module,
    load_conforming_provider,
)

from ..config import ProviderInfo, settings

__all__ = [
    "ProviderCompatibility",
    "ProviderDescriptor",
    "ProviderHandle",
    "ProviderMetadata",
    "available_providers",
    "load_provider",
    "provider_descriptors",
    "refresh_provider_cache",
]

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderMetadata:
    """Publicly exposable metadata describing a configured provider."""

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
    """A loaded provider instance and, when available, validated SDK evidence."""

    instance: Any
    metadata: ProviderMetadata
    manifest: ProviderManifest | None = None
    conformance: ProviderConformanceReport | None = None
    governance: dict[str, object] | None = None


@dataclass(frozen=True)
class ProviderCompatibility:
    """Compatibility status between a provider and the application API."""

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
    """Extended public view of configured provider metadata."""

    metadata: ProviderMetadata
    module: str
    version: str | None
    compatibility: ProviderCompatibility
    manifest: ProviderManifest | None
    conformance: ProviderConformanceReport

    def to_dict(self) -> dict[str, object]:
        """Return serialisable compatibility and conformance evidence."""

        payload = self.metadata.to_dict()
        payload.update(
            {
                "module": self.module,
                "version": self.version,
                "compatibility": self.compatibility.to_dict(),
                "manifest": self.manifest.to_dict() if self.manifest is not None else None,
                "conformance": self.conformance.to_dict(),
            }
        )
        return payload


ProviderSignature = tuple[str, str, str, str | None, tuple[str, ...]]
_VERSION_PATTERN = re.compile(r"^(?P<major>\d+)")


def _provider_signature() -> tuple[ProviderSignature, ...]:
    """Return a hashable snapshot of the configured provider allowlist."""

    snapshot: list[ProviderSignature] = []
    for key, info in settings.allowed_providers.items():
        snapshot.append(
            (
                key,
                info.module,
                info.name,
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
    signature: tuple[ProviderSignature, ...], capability: str | None
) -> tuple[ProviderMetadata, ...]:
    """Build provider metadata lists keyed by capability filters."""

    metadata: list[ProviderMetadata] = []
    for key, _, _, _, _capabilities in signature:
        info = settings.allowed_providers.get(key)
        if info is None:
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
    """Extract a declared provider version without exposing import details."""

    try:
        module = importlib.import_module(module_path)
    except Exception as exc:  # pragma: no cover - defensive log path
        logger.debug(
            "Unable to import provider module for version detection",
            extra={"module": module_path, "error_type": type(exc).__name__},
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
    return int(match.group("major"))


def _compatibility(
    provider_version: str | None,
    conformance: ProviderConformanceReport,
) -> ProviderCompatibility:
    if not conformance.passed:
        codes = ", ".join(conformance.failure_codes) or "unknown"
        return ProviderCompatibility(
            api_version=API_VERSION,
            provider_version=provider_version,
            status="incompatible",
            reason=f"provider conformance failed: {codes}",
        )

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
    signature: tuple[ProviderSignature, ...],
    capability: str | None,
) -> tuple[ProviderDescriptor, ...]:
    """Build provider descriptors with structural conformance evidence."""

    descriptors: list[ProviderDescriptor] = []
    for key, module, _, _, _capabilities in signature:
        info = settings.allowed_providers.get(key)
        if info is None:
            continue
        metadata = _metadata_from_info(key, info)
        if capability and capability not in metadata.capabilities:
            continue
        conformance = inspect_provider_module(
            module,
            expected_key=key,
            expected_capabilities=metadata.capabilities,
            api_version=API_VERSION,
        )
        manifest = conformance.manifest
        version = manifest.version if manifest is not None else _provider_version(module)
        descriptors.append(
            ProviderDescriptor(
                metadata=metadata,
                module=module,
                version=version,
                compatibility=_compatibility(version, conformance),
                manifest=manifest,
                conformance=conformance,
            )
        )

    descriptors.sort(key=lambda item: item.metadata.key)

    incompatible = [descriptor for descriptor in descriptors if descriptor.compatibility.status == "incompatible"]
    if incompatible:
        logger.warning(
            "Incompatible providers detected",
            extra={
                "providers": [
                    {
                        "key": descriptor.metadata.key,
                        "module": descriptor.module,
                        "provider_version": descriptor.version,
                        "reason": descriptor.compatibility.reason,
                    }
                    for descriptor in incompatible
                ]
            },
        )

    return tuple(descriptors)


def provider_descriptors(capability: str | None = None) -> list[ProviderDescriptor]:
    """Return provider descriptors including conformance summaries."""

    signature = _provider_signature()
    return list(_cached_provider_descriptors(signature, capability))


def load_provider(key: str, factory: str = "provider") -> ProviderHandle:
    """Load an allowlisted provider through the conformance boundary."""

    if not key:
        raise ValueError("Provider key is required")

    try:
        info = settings.allowed_providers[key]
    except KeyError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Provider '{key}' is not allowed") from exc

    metadata = _metadata_from_info(key, info)
    try:
        conforming = load_conforming_provider(
            info.module,
            expected_key=key,
            expected_capabilities=metadata.capabilities,
            api_version=API_VERSION,
            factory_name=factory,
        )
    except ProviderConformanceError as exc:
        codes = ", ".join(exc.report.failure_codes) or "unknown"
        raise ValueError(f"Provider '{key}' failed conformance: {codes}") from exc

    return ProviderHandle(
        instance=conforming.instance,
        metadata=metadata,
        manifest=conforming.manifest,
        conformance=conforming.report,
    )


def refresh_provider_cache() -> None:
    """Invalidate cached provider metadata and conformance snapshots."""

    _cached_provider_metadata.cache_clear()
    _cached_provider_descriptors.cache_clear()
