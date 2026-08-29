"""Exact, deterministic SDK and application API compatibility decisions."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import PROVIDER_SDK_VERSION, ProviderManifest

SDK_DISTRIBUTION_VERSION = "0.5.0"
SCAFFOLD_VERSION = SDK_DISTRIBUTION_VERSION


@dataclass(frozen=True, slots=True)
class CompatibilityResult:
    """Stable compatibility evidence for one provider manifest."""

    compatible: bool
    code: str
    message: str

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "compatible": self.compatible, "message": self.message}


def application_api_major(api_version: str) -> int | None:
    """Parse the application API major without accepting ranges."""

    first = api_version.split(".", 1)[0].strip()
    return int(first) if first.isdigit() else None


def check_compatibility(manifest: ProviderManifest, *, api_version: str) -> CompatibilityResult:
    """Require the exact SDK contract and exact application API major."""

    if manifest.sdk_version != PROVIDER_SDK_VERSION:
        return CompatibilityResult(False, "sdk.contract.mismatch", "provider SDK contract does not match")
    major = application_api_major(api_version)
    if major is None:
        return CompatibilityResult(False, "api.version.invalid", "application API version is invalid")
    if manifest.api_major != major:
        return CompatibilityResult(False, "api.major.mismatch", "provider application API major does not match")
    return CompatibilityResult(True, "compatible", "provider contract is compatible")
