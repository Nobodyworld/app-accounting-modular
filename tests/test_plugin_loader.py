"""Plugin loader tests verifying provider discovery and validation semantics."""

from __future__ import annotations

import sys
import types

import pytest

from apps.api.config import ProviderInfo, settings
from apps.api.services.plugin_loader import (
    available_providers,
    load_provider,
    refresh_provider_cache,
)


def test_available_providers_returns_metadata() -> None:
    """Providers should expose metadata entries for configured capabilities."""
    refresh_provider_cache()
    providers = available_providers()
    keys = {meta.key for meta in providers}
    assert "fx:ecb" in keys
    assert "market:yfinance" in keys


def test_load_provider_instantiates_provider() -> None:
    """Provider handles should return initialised provider instances."""
    refresh_provider_cache()
    handle = load_provider("fx:ecb")
    assert hasattr(handle.instance, "name")
    assert handle.metadata.key == "fx:ecb"


def test_load_provider_rejects_unknown_key() -> None:
    """Invalid provider keys must raise descriptive errors."""
    with pytest.raises(ValueError):
        load_provider("plugins.fx_ecb.provider")

    with pytest.raises(ValueError):
        load_provider("unknown")


def test_load_provider_rejects_missing_modules(monkeypatch) -> None:
    """Missing provider modules should result in ValueError responses."""
    refresh_provider_cache()
    monkeypatch.setattr(
        settings,
        "allowed_providers",
        {
            "broken": ProviderInfo(
                module="plugins.does_not_exist",
                name="Broken",
                capabilities=(),
            )
        },
    )

    with pytest.raises(ValueError):
        load_provider("broken")


def test_load_provider_requires_factory(monkeypatch) -> None:
    """Named factories must exist within the provider module namespace."""
    refresh_provider_cache()
    monkeypatch.setattr(settings, "allowed_providers", settings.allowed_providers.copy())

    with pytest.raises(ValueError):
        load_provider("fx:ecb", factory="missing")


def test_load_provider_rejects_non_callable(monkeypatch) -> None:
    """Provider factories should be callable objects."""
    refresh_provider_cache()
    module = types.ModuleType("plugins.dummy_module")
    module.provider = "not-callable"
    monkeypatch.setitem(sys.modules, "plugins.dummy_module", module)
    monkeypatch.setattr(
        settings,
        "allowed_providers",
        {
            "dummy": ProviderInfo(
                module="plugins.dummy_module",
                name="Dummy",
                capabilities=(),
            )
        },
    )

    with pytest.raises(ValueError):
        load_provider("dummy")


def test_load_provider_rejects_none(monkeypatch) -> None:
    """Factories returning ``None`` should be rejected early."""
    refresh_provider_cache()
    module = types.ModuleType("plugins.dummy_none")

    def factory():
        return None

    module.provider = factory
    monkeypatch.setitem(sys.modules, "plugins.dummy_none", module)
    monkeypatch.setattr(
        settings,
        "allowed_providers",
        {
            "dummy": ProviderInfo(
                module="plugins.dummy_none",
                name="Dummy",
                capabilities=(),
            )
        },
    )

    with pytest.raises(ValueError):
        load_provider("dummy")


def test_available_providers_cache_invalidation(monkeypatch) -> None:
    """Refresh operations should rebuild provider cache after config changes."""
    refresh_provider_cache()
    baseline = available_providers()
    assert baseline

    monkeypatch.setattr(
        settings,
        "allowed_providers",
        {
            "custom": ProviderInfo(
                module="plugins.tax_oecd_stub.provider",
                name="Custom",
                capabilities=("tax",),
            )
        },
    )

    refresh_provider_cache()
    providers = available_providers()
    assert [meta.key for meta in providers] == ["custom"]


def test_load_provider_validates_required_methods(monkeypatch) -> None:
    """Providers lacking capability-specific methods must raise errors."""
    refresh_provider_cache()
    module = types.ModuleType("plugins.invalid_fx")

    class InvalidProvider:
        name = "invalid"

    def factory() -> InvalidProvider:
        return InvalidProvider()

    module.provider = factory
    monkeypatch.setitem(sys.modules, "plugins.invalid_fx", module)
    monkeypatch.setattr(
        settings,
        "allowed_providers",
        {
            "invalid": ProviderInfo(
                module="plugins.invalid_fx",
                name="Invalid",
                capabilities=("fx",),
            )
        },
    )

    refresh_provider_cache()
    with pytest.raises(ValueError) as excinfo:
        load_provider("invalid")
    assert "sync_daily_rates" in str(excinfo.value)


# TODO - (plugins) Validate async provider initialisation when supported.


def test_load_provider_requires_name_attribute(monkeypatch) -> None:
    refresh_provider_cache()
    module = types.ModuleType("plugins.nameless")

    class NamelessProvider:
        sync_daily_rates = lambda self, *args, **kwargs: None  # type: ignore[assignment]

    def factory() -> NamelessProvider:
        return NamelessProvider()

    module.provider = factory
    monkeypatch.setitem(sys.modules, "plugins.nameless", module)
    monkeypatch.setattr(
        settings,
        "allowed_providers",
        {
            "nameless": ProviderInfo(
                module="plugins.nameless",
                name="Nameless",
                capabilities=("fx",),
            )
        },
    )

    refresh_provider_cache()
    with pytest.raises(ValueError) as excinfo:
        load_provider("nameless")
    assert "name" in str(excinfo.value)
