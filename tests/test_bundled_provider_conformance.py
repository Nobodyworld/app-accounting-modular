from __future__ import annotations

import importlib
from types import ModuleType

import pytest

from apps.api.config import settings
from apps.api.services.plugin_loader import provider_descriptors, refresh_provider_cache
from apps.api.version import API_VERSION
from apps.provider_sdk import inspect_provider_module

EXPECTED_POLICIES = {
    "bank:plaid_demo": ("none", (), "controlled-sample"),
    "fx:ecb": ("https", (), "public-reference"),
    "fx:openexchangerates": ("https", ("OPENEXCHANGERATES_APP_ID",), "external-service"),
    "macro:fred_demo": ("none", (), "controlled-sample"),
    "market:commodities_demo": ("none", (), "controlled-sample"),
    "market:yfinance": ("https", (), "external-service"),
    "tax:oecd_demo": ("none", (), "controlled-sample"),
    "tax:oecd_vat": ("none", (), "controlled-sample"),
    "tax:us_tables": ("none", (), "controlled-sample"),
}


def _forbidden_network(*args: object, **kwargs: object) -> None:
    raise AssertionError("structural conformance must not perform network access")


def _block_network_entrypoints(monkeypatch: pytest.MonkeyPatch, module: ModuleType) -> None:
    if hasattr(module, "get_bounded_json"):
        monkeypatch.setattr(module, "get_bounded_json", _forbidden_network)
    yfinance = getattr(module, "yf", None)
    if yfinance is not None and hasattr(yfinance, "download"):
        monkeypatch.setattr(yfinance, "download", _forbidden_network)


@pytest.mark.parametrize("key", sorted(EXPECTED_POLICIES))
def test_configured_bundled_provider_conforms_without_network(
    key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    info = settings.allowed_providers[key]
    module = importlib.import_module(info.module)
    _block_network_entrypoints(monkeypatch, module)

    report = inspect_provider_module(
        module,
        expected_key=key,
        expected_capabilities=tuple(info.capabilities),
        api_version=API_VERSION,
    )

    assert report.passed, report.to_json()
    assert report.manifest is not None
    assert report.manifest.key == key
    assert report.manifest.capabilities == tuple(sorted(info.capabilities))
    assert report.manifest.version == "0.3.0"
    assert report.manifest.license == "Apache-2.0"
    policy, credential_env, classification = EXPECTED_POLICIES[key]
    assert report.manifest.network_policy == policy
    assert report.manifest.credential_env == credential_env
    assert report.manifest.data_classification == classification


def test_every_configured_provider_has_a_policy_entry() -> None:
    assert set(settings.allowed_providers) == set(EXPECTED_POLICIES)


def test_provider_descriptors_expose_passing_bundled_conformance() -> None:
    refresh_provider_cache()
    descriptors = provider_descriptors()

    assert [descriptor.metadata.key for descriptor in descriptors] == sorted(EXPECTED_POLICIES)
    assert all(descriptor.conformance.passed for descriptor in descriptors)
    assert all(descriptor.manifest is not None for descriptor in descriptors)
    assert all(descriptor.compatibility.status == "compatible" for descriptor in descriptors)
