"""Plugin loader tests verifying provider discovery and validation semantics."""

from __future__ import annotations

import sys
import types

import pytest
from apps.api.config import ProviderInfo, settings
from apps.api.services.plugin_loader import (
    available_providers,
    load_provider,
    provider_descriptors,
    refresh_provider_cache,
)
from apps.provider_sdk import ProviderManifest


def _manifest(key: str, capabilities: tuple[str, ...]) -> ProviderManifest:
    return ProviderManifest(
        key=key,
        name=f"Test provider {key}",
        version="0.0.0",
        api_major=0,
        capabilities=capabilities,
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
    module.PROVIDER_MANIFEST = _manifest("test:dummy", ("fx",))
    module.provider = "not-callable"
    monkeypatch.setitem(sys.modules, "plugins.dummy_module", module)
    monkeypatch.setattr(
        settings,
        "allowed_providers",
        {
            "test:dummy": ProviderInfo(
                module="plugins.dummy_module",
                name="Dummy",
                capabilities=("fx",),
            )
        },
    )

    with pytest.raises(ValueError):
        load_provider("test:dummy")


def test_load_provider_rejects_none(monkeypatch) -> None:
    """Factories returning ``None`` should be rejected early."""
    refresh_provider_cache()
    module = types.ModuleType("plugins.dummy_none")
    module.PROVIDER_MANIFEST = _manifest("test:none", ("fx",))

    def factory():
        return None

    module.provider = factory
    monkeypatch.setitem(sys.modules, "plugins.dummy_none", module)
    monkeypatch.setattr(
        settings,
        "allowed_providers",
        {
            "test:none": ProviderInfo(
                module="plugins.dummy_none",
                name="Dummy",
                capabilities=("fx",),
            )
        },
    )

    with pytest.raises(ValueError):
        load_provider("test:none")


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
    module.PROVIDER_MANIFEST = _manifest("test:invalid_fx", ("fx",))

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
            "test:invalid_fx": ProviderInfo(
                module="plugins.invalid_fx",
                name="Invalid",
                capabilities=("fx",),
            )
        },
    )

    refresh_provider_cache()
    with pytest.raises(ValueError) as excinfo:
        load_provider("test:invalid_fx")
    assert "sync_daily_rates" in str(excinfo.value)


# TODO[P3][2d]: (plugins) Validate async provider initialisation when supported.


def test_load_provider_requires_name_attribute(monkeypatch) -> None:
    refresh_provider_cache()
    module = types.ModuleType("plugins.nameless")
    module.PROVIDER_MANIFEST = _manifest("test:nameless", ("fx",))

    class NamelessProvider:
        def sync_daily_rates(self, *args: object, **kwargs: object) -> None:  # type: ignore[unused-argument]
            return None

    def factory() -> NamelessProvider:
        return NamelessProvider()

    module.provider = factory
    monkeypatch.setitem(sys.modules, "plugins.nameless", module)
    monkeypatch.setattr(
        settings,
        "allowed_providers",
        {
            "test:nameless": ProviderInfo(
                module="plugins.nameless",
                name="Nameless",
                capabilities=("fx",),
            )
        },
    )

    refresh_provider_cache()
    with pytest.raises(ValueError) as excinfo:
        load_provider("test:nameless")
    assert "name" in str(excinfo.value)


def test_provider_descriptors_include_versions_and_compatibility(monkeypatch) -> None:
    """Provider descriptors should expose compatibility summaries."""

    module = types.ModuleType("plugins.versioned_provider")
    module.__version__ = "2.0.0"
    monkeypatch.setitem(sys.modules, "plugins.versioned_provider", module)
    monkeypatch.setattr(
        settings,
        "allowed_providers",
        {
            "versioned": ProviderInfo(
                module="plugins.versioned_provider",
                name="Versioned",
                capabilities=(),
            )
        },
    )
    monkeypatch.setattr("apps.api.services.plugin_loader.API_VERSION", "1.0.0")

    refresh_provider_cache()
    descriptors = provider_descriptors()
    assert len(descriptors) == 1
    payload = descriptors[0].to_dict()
    assert payload["version"] == "2.0.0"
    assert payload["compatibility"]["api_version"] == "1.0.0"
    assert payload["compatibility"]["status"] == "incompatible"


def test_provider_descriptors_emit_warning_on_incompatible(monkeypatch, caplog) -> None:
    """Incompatible providers should trigger an alert log for observability."""

    module = types.ModuleType("plugins.incompatible_provider")
    module.__version__ = "3.0.0"
    monkeypatch.setitem(sys.modules, "plugins.incompatible_provider", module)
    monkeypatch.setattr(
        settings,
        "allowed_providers",
        {
            "incompatible": ProviderInfo(
                module="plugins.incompatible_provider",
                name="Incompatible",
                capabilities=(),
            )
        },
    )
    monkeypatch.setattr("apps.api.services.plugin_loader.API_VERSION", "0.0.0")

    refresh_provider_cache()
    caplog.set_level("WARNING", logger="apps.api.services.plugin_loader")

    descriptors = provider_descriptors()
    assert descriptors

    records = [record for record in caplog.records if record.message == "Incompatible providers detected"]
    assert records
    providers = records[0].providers
    assert providers[0]["key"] == "incompatible"


def test_load_provider_handles_async_factory(monkeypatch) -> None:
    """Async provider factories should raise a clear error until supported."""

    refresh_provider_cache()
    module = types.ModuleType("plugins.async_factory")
    module.PROVIDER_MANIFEST = _manifest("test:async", ("fx",))

    async def factory():
        return object()

    module.provider = factory
    monkeypatch.setitem(sys.modules, "plugins.async_factory", module)
    monkeypatch.setattr(
        settings,
        "allowed_providers",
        {
            "test:async": ProviderInfo(
                module="plugins.async_factory",
                name="AsyncProvider",
                capabilities=("fx",),
            )
        },
    )

    with pytest.raises(ValueError):
        load_provider("test:async")
