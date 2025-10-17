from __future__ import annotations

import sys
import types

import pytest

from apps.api.config import ProviderInfo, settings
from apps.api.services.plugin_loader import available_providers, load_provider


def test_available_providers_returns_metadata() -> None:
    providers = available_providers()
    keys = {meta.key for meta in providers}
    assert "fx:ecb" in keys
    assert "market:yfinance" in keys


def test_load_provider_instantiates_provider() -> None:
    handle = load_provider("fx:ecb")
    assert hasattr(handle.instance, "name")
    assert handle.metadata.key == "fx:ecb"


def test_load_provider_rejects_unknown_key() -> None:
    with pytest.raises(ValueError):
        load_provider("plugins.fx_ecb.provider")

    with pytest.raises(ValueError):
        load_provider("unknown")


def test_load_provider_rejects_missing_modules(monkeypatch) -> None:
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
    monkeypatch.setattr(settings, "allowed_providers", settings.allowed_providers.copy())

    with pytest.raises(ValueError):
        load_provider("fx:ecb", factory="missing")


def test_load_provider_rejects_non_callable(monkeypatch) -> None:
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
