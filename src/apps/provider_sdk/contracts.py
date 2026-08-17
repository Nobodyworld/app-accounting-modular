"""Public contracts for Modular Accounting provider packages."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, Protocol, runtime_checkable

PROVIDER_SDK_VERSION = "1.0"

ProviderCapability = Literal["bank", "fx", "macro", "market", "tax"]
NetworkPolicy = Literal["none", "https"]
DataClassification = Literal["controlled-sample", "external-service", "public-reference"]

SUPPORTED_CAPABILITIES: tuple[ProviderCapability, ...] = ("bank", "fx", "macro", "market", "tax")
NETWORK_POLICIES: tuple[NetworkPolicy, ...] = ("none", "https")
DATA_CLASSIFICATIONS: tuple[DataClassification, ...] = (
    "controlled-sample",
    "external-service",
    "public-reference",
)

CAPABILITY_METHODS: Mapping[str, tuple[str, ...]] = {
    "bank": ("fetch_transactions", "list_accounts"),
    "fx": ("sync_daily_rates",),
    "macro": ("fetch_series",),
    "market": ("fetch_prices",),
    "tax": ("upsert_rules",),
}

CAPABILITY_PARAMETERS: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "bank": {
        "fetch_transactions": ("account_id", "start", "end"),
        "list_accounts": (),
    },
    "fx": {"sync_daily_rates": ("base", "date_")},
    "macro": {"fetch_series": ("series_id", "start", "end")},
    "market": {"fetch_prices": ("symbol", "start", "end")},
    "tax": {"upsert_rules": ()},
}

_KEY_PATTERN = re.compile(r"^[a-z0-9]+:[a-z0-9]+(?:[-_][a-z0-9]+)*$")
_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_SDK_VERSION_PATTERN = re.compile(r"^\d+\.\d+$")
_FACTORY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ENV_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


class ProviderManifestError(ValueError):
    """Raised when provider manifest metadata is invalid."""


def _normalise_text(value: str | None, *, field_name: str, maximum: int, required: bool) -> str | None:
    if value is None:
        if required:
            raise ProviderManifestError(f"{field_name} is required")
        return None
    if not isinstance(value, str):
        raise ProviderManifestError(f"{field_name} must be text")
    cleaned = value.strip()
    if required and not cleaned:
        raise ProviderManifestError(f"{field_name} is required")
    if not cleaned:
        return None
    if len(cleaned) > maximum:
        raise ProviderManifestError(f"{field_name} exceeds {maximum} characters")
    return cleaned


def _normalise_values(values: Iterable[str], *, field_name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise ProviderManifestError(f"{field_name} must be a sequence of text values")
    cleaned: list[str] = []
    try:
        for value in values:
            if not isinstance(value, str):
                raise ProviderManifestError(f"{field_name} entries must be text")
            item = value.strip()
            if not item:
                raise ProviderManifestError(f"{field_name} entries must not be empty")
            cleaned.append(item)
    except TypeError as exc:
        raise ProviderManifestError(f"{field_name} must be a sequence of text values") from exc
    return tuple(sorted(cleaned))


@dataclass(frozen=True, slots=True)
class ProviderManifest:
    """Bounded, immutable metadata declared by a provider package."""

    key: str
    name: str
    version: str
    api_major: int
    capabilities: tuple[str, ...]
    factory: str = "provider"
    sdk_version: str = PROVIDER_SDK_VERSION
    description: str | None = None
    homepage: str | None = None
    license: str | None = None
    network_policy: NetworkPolicy = "none"
    credential_env: tuple[str, ...] = ()
    data_classification: DataClassification = "controlled-sample"

    def __post_init__(self) -> None:
        key = _normalise_text(self.key, field_name="key", maximum=96, required=True)
        assert key is not None
        if _KEY_PATTERN.fullmatch(key) is None:
            raise ProviderManifestError(
                "key must follow 'namespace:slug' using lowercase letters, numbers, hyphens, and underscores"
            )

        name = _normalise_text(self.name, field_name="name", maximum=128, required=True)
        version = _normalise_text(self.version, field_name="version", maximum=64, required=True)
        factory = _normalise_text(self.factory, field_name="factory", maximum=64, required=True)
        sdk_version = _normalise_text(
            self.sdk_version,
            field_name="sdk_version",
            maximum=16,
            required=True,
        )
        assert name is not None
        assert version is not None
        assert factory is not None
        assert sdk_version is not None

        if _VERSION_PATTERN.fullmatch(version) is None:
            raise ProviderManifestError("version must be semantic version text such as '0.1.0'")
        if _SDK_VERSION_PATTERN.fullmatch(sdk_version) is None:
            raise ProviderManifestError("sdk_version must use '<major>.<minor>'")
        if _FACTORY_PATTERN.fullmatch(factory) is None:
            raise ProviderManifestError("factory must be a Python identifier")
        if (
            not isinstance(self.api_major, int)
            or isinstance(self.api_major, bool)
            or not 0 <= self.api_major <= 999
        ):
            raise ProviderManifestError("api_major must be an integer between 0 and 999")

        capabilities = _normalise_values(self.capabilities, field_name="capabilities")
        if not capabilities:
            raise ProviderManifestError("at least one capability is required")
        if len(capabilities) != len(set(capabilities)):
            raise ProviderManifestError("capabilities must be unique")
        unknown = tuple(capability for capability in capabilities if capability not in SUPPORTED_CAPABILITIES)
        if unknown:
            raise ProviderManifestError(f"unsupported capabilities: {', '.join(unknown)}")

        if self.network_policy not in NETWORK_POLICIES:
            raise ProviderManifestError("network_policy must be 'none' or 'https'")
        if self.data_classification not in DATA_CLASSIFICATIONS:
            raise ProviderManifestError("unsupported data_classification")

        credential_env = (
            _normalise_values(self.credential_env, field_name="credential_env") if self.credential_env else ()
        )
        if len(credential_env) != len(set(credential_env)):
            raise ProviderManifestError("credential_env names must be unique")
        for variable_name in credential_env:
            if _ENV_PATTERN.fullmatch(variable_name) is None:
                raise ProviderManifestError(
                    "credential_env entries must be uppercase environment-variable names"
                )
        if credential_env and self.network_policy == "none":
            raise ProviderManifestError("credential_env requires network_policy='https'")

        description = _normalise_text(
            self.description,
            field_name="description",
            maximum=512,
            required=False,
        )
        homepage = _normalise_text(
            self.homepage,
            field_name="homepage",
            maximum=256,
            required=False,
        )
        license_name = _normalise_text(
            self.license,
            field_name="license",
            maximum=64,
            required=False,
        )
        if homepage is not None and not homepage.startswith("https://"):
            raise ProviderManifestError("homepage must use HTTPS")

        object.__setattr__(self, "key", key)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "factory", factory)
        object.__setattr__(self, "sdk_version", sdk_version)
        object.__setattr__(self, "capabilities", capabilities)
        object.__setattr__(self, "credential_env", credential_env)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "homepage", homepage)
        object.__setattr__(self, "license", license_name)

    def to_dict(self) -> dict[str, object]:
        """Return deterministic, JSON-compatible public metadata."""

        return {
            "key": self.key,
            "name": self.name,
            "version": self.version,
            "api_major": self.api_major,
            "capabilities": list(self.capabilities),
            "factory": self.factory,
            "sdk_version": self.sdk_version,
            "description": self.description,
            "homepage": self.homepage,
            "license": self.license,
            "network_policy": self.network_policy,
            "credential_env": list(self.credential_env),
            "data_classification": self.data_classification,
        }


def required_methods(capabilities: Iterable[str]) -> tuple[str, ...]:
    """Return the sorted capability method set."""

    methods: set[str] = set()
    for capability in capabilities:
        methods.update(CAPABILITY_METHODS.get(capability, ()))
    return tuple(sorted(methods))


@runtime_checkable
class FXProvider(Protocol):
    name: str

    def sync_daily_rates(self, base: str = "USD", date_: date | None = None) -> Iterable[Any]: ...


@runtime_checkable
class MarketProvider(Protocol):
    name: str

    def fetch_prices(self, symbol: str, start: date, end: date) -> Iterable[Any]: ...


@runtime_checkable
class TaxProvider(Protocol):
    name: str

    def upsert_rules(self) -> Iterable[Any]: ...


@runtime_checkable
class MacroProvider(Protocol):
    name: str

    def fetch_series(self, series_id: str, start: date, end: date) -> Iterable[tuple[date, float]]: ...


@runtime_checkable
class BankProvider(Protocol):
    name: str

    def list_accounts(self) -> list[dict[str, Any]]: ...

    def fetch_transactions(
        self,
        account_id: str,
        start: date,
        end: date,
    ) -> Iterable[dict[str, Any]]: ...
