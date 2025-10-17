from __future__ import annotations

import sys
import types

import pytest

from apps.api.services.plugin_loader import available_plugins, load_provider


def test_available_plugins_returns_module_paths() -> None:
    plugins = available_plugins()
    assert "plugins.fx_ecb.provider" in plugins
    assert "plugins.market_yfinance.provider" in plugins


def test_load_provider_instantiates_provider() -> None:
    provider = load_provider("plugins.fx_ecb.provider")
    assert hasattr(provider, "name")


def test_load_provider_rejects_missing_modules() -> None:
    with pytest.raises(ValueError):
        load_provider("plugins.does_not_exist")


def test_load_provider_requires_factory() -> None:
    with pytest.raises(ValueError):
        load_provider("plugins.fx_ecb.provider", factory="missing")


def test_load_provider_rejects_non_callable(monkeypatch) -> None:
    module = types.ModuleType("plugins.dummy_module")
    module.provider = "not-callable"
    monkeypatch.setitem(sys.modules, "plugins.dummy_module", module)

    with pytest.raises(ValueError):
        load_provider("plugins.dummy_module")


def test_load_provider_rejects_none(monkeypatch) -> None:
    module = types.ModuleType("plugins.dummy_none")

    def factory():
        return None

    module.provider = factory
    monkeypatch.setitem(sys.modules, "plugins.dummy_none", module)

    with pytest.raises(ValueError):
        load_provider("plugins.dummy_none")
