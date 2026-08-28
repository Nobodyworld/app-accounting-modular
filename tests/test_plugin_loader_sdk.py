from __future__ import annotations

import sys
from datetime import date
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from apps.api.config import ProviderInfo
from apps.api.services import plugin_loader
from apps.provider_sdk import ProviderManifest


class MarketProvider:
    name = "market"

    def fetch_prices(self, symbol: str, start: date, end: date) -> list[object]:
        return []


class MacroProvider:
    name = "macro"

    def fetch_series(self, series_id: str, start: date, end: date) -> list[tuple[date, float]]:
        return []


class BankProvider:
    name = "bank"

    def list_accounts(self) -> list[dict[str, object]]:
        return []

    def fetch_transactions(
        self,
        account_id: str,
        start: date,
        end: date,
    ) -> list[dict[str, object]]:
        return []


def module_for(
    module_name: str,
    *,
    key: str = "market:demo",
    capabilities: tuple[str, ...] = ("market",),
    provider_type: type[Any] = MarketProvider,
    version: str = "0.3.0",
) -> ModuleType:
    module = ModuleType(module_name)
    module.__version__ = version
    module.PROVIDER_MANIFEST = ProviderManifest(
        key=key,
        name="Demo Provider",
        version=version,
        api_major=0,
        capabilities=capabilities,
    )

    def provider() -> provider_type:  # type: ignore[valid-type]
        return provider_type()

    provider.__annotations__["return"] = provider_type
    module.provider = provider
    return module


def configure(monkeypatch: pytest.MonkeyPatch, **providers: ProviderInfo) -> None:
    monkeypatch.setattr(plugin_loader, "settings", SimpleNamespace(allowed_providers=providers))
    plugin_loader.refresh_provider_cache()


def install(monkeypatch: pytest.MonkeyPatch, module: ModuleType) -> None:
    monkeypatch.setitem(sys.modules, module.__name__, module)


def test_available_providers_is_sorted_filterable_and_tracks_name_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure(
        monkeypatch,
        **{
            "market:z": ProviderInfo(module="plugins.z", name="Z", capabilities=("market",)),
            "bank:a": ProviderInfo(module="plugins.a", name="A", capabilities=("bank",)),
        },
    )
    assert [item.key for item in plugin_loader.available_providers()] == ["bank:a", "market:z"]
    assert [item.key for item in plugin_loader.available_providers("market")] == ["market:z"]

    plugin_loader.settings.allowed_providers["market:z"].name = "Renamed"
    assert plugin_loader.available_providers("market")[0].name == "Renamed"


def test_load_provider_returns_manifest_and_conformance(monkeypatch: pytest.MonkeyPatch) -> None:
    module = module_for("plugins.market_demo.provider")
    install(monkeypatch, module)
    configure(
        monkeypatch,
        **{
            "market:demo": ProviderInfo(
                module=module.__name__,
                name="Demo",
                capabilities=("market",),
            )
        },
    )

    handle = plugin_loader.load_provider("market:demo")

    assert isinstance(handle.instance, MarketProvider)
    assert handle.metadata.key == "market:demo"
    assert handle.manifest.key == "market:demo"
    assert handle.conformance.passed


def test_load_provider_rejects_blank_unknown_and_module_path_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    configure(monkeypatch)
    with pytest.raises(ValueError, match="required"):
        plugin_loader.load_provider("")
    with pytest.raises(ValueError, match="not allowed"):
        plugin_loader.load_provider("market:missing")
    with pytest.raises(ValueError, match="not allowed"):
        plugin_loader.load_provider("plugins.market_demo.provider")


def test_load_provider_fails_closed_on_missing_module_without_raw_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure(
        monkeypatch,
        **{
            "market:missing": ProviderInfo(
                module="plugins.missing.provider",
                name="Missing",
                capabilities=("market",),
            )
        },
    )
    with pytest.raises(ValueError) as exc_info:
        plugin_loader.load_provider("market:missing")
    assert str(exc_info.value) == "Provider 'market:missing' failed conformance: module.import"
    assert "secret_module" not in str(exc_info.value)


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (lambda module: delattr(module, "PROVIDER_MANIFEST"), "manifest.present"),
        (
            lambda module: setattr(
                module,
                "PROVIDER_MANIFEST",
                ProviderManifest(
                    key="market:different",
                    name="Different",
                    version="0.3.0",
                    api_major=0,
                    capabilities=("market",),
                ),
            ),
            "manifest.key",
        ),
        (
            lambda module: setattr(
                module,
                "PROVIDER_MANIFEST",
                ProviderManifest(
                    key="market:demo",
                    name="Different",
                    version="0.3.0",
                    api_major=0,
                    capabilities=("tax",),
                ),
            ),
            "manifest.capabilities",
        ),
        (lambda module: setattr(module, "provider", None), "factory.callable"),
    ],
)
def test_load_provider_surfaces_stable_conformance_codes(
    monkeypatch: pytest.MonkeyPatch,
    mutation: Any,
    expected_code: str,
) -> None:
    module = module_for("plugins.mutated.provider")
    mutation(module)
    install(monkeypatch, module)
    configure(
        monkeypatch,
        **{
            "market:demo": ProviderInfo(
                module=module.__name__,
                name="Demo",
                capabilities=("market",),
            )
        },
    )

    with pytest.raises(ValueError) as exc_info:
        plugin_loader.load_provider("market:demo")
    assert expected_code in str(exc_info.value)


def test_load_provider_rejects_wrong_factory_override(monkeypatch: pytest.MonkeyPatch) -> None:
    module = module_for("plugins.factory_override.provider")
    install(monkeypatch, module)
    configure(
        monkeypatch,
        **{
            "market:demo": ProviderInfo(
                module=module.__name__,
                name="Demo",
                capabilities=("market",),
            )
        },
    )
    with pytest.raises(ValueError, match="factory.manifest"):
        plugin_loader.load_provider("market:demo", factory="build")


def test_macro_and_bank_capabilities_load_through_same_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    macro = module_for(
        "plugins.macro_demo.provider",
        key="macro:demo",
        capabilities=("macro",),
        provider_type=MacroProvider,
    )
    bank = module_for(
        "plugins.bank_demo.provider",
        key="bank:demo",
        capabilities=("bank",),
        provider_type=BankProvider,
    )
    install(monkeypatch, macro)
    install(monkeypatch, bank)
    configure(
        monkeypatch,
        **{
            "macro:demo": ProviderInfo(module=macro.__name__, name="Macro", capabilities=("macro",)),
            "bank:demo": ProviderInfo(module=bank.__name__, name="Bank", capabilities=("bank",)),
        },
    )

    assert plugin_loader.load_provider("macro:demo").conformance.passed
    assert plugin_loader.load_provider("bank:demo").conformance.passed


def test_provider_descriptors_expose_structural_evidence_without_invoking_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = module_for("plugins.descriptor.provider")

    def forbidden() -> MarketProvider:
        raise AssertionError("descriptor inspection must not invoke factory")

    forbidden.__annotations__["return"] = MarketProvider
    module.provider = forbidden
    install(monkeypatch, module)
    configure(
        monkeypatch,
        **{
            "market:demo": ProviderInfo(
                module=module.__name__,
                name="Demo",
                capabilities=("market",),
            )
        },
    )

    descriptor = plugin_loader.provider_descriptors()[0]
    payload = descriptor.to_dict()

    assert descriptor.conformance.passed
    assert payload["manifest"]["key"] == "market:demo"
    assert payload["conformance"]["passed"] is True
    assert payload["compatibility"]["status"] == "compatible"


def test_nonconforming_descriptor_is_marked_incompatible(monkeypatch: pytest.MonkeyPatch) -> None:
    module = module_for("plugins.nonconforming.provider")
    module.provider = None
    install(monkeypatch, module)
    configure(
        monkeypatch,
        **{
            "market:demo": ProviderInfo(
                module=module.__name__,
                name="Demo",
                capabilities=("market",),
            )
        },
    )

    descriptor = plugin_loader.provider_descriptors()[0]

    assert descriptor.compatibility.status == "incompatible"
    assert descriptor.compatibility.reason == "provider conformance failed: factory.callable"


def test_legacy_version_compatibility_is_preserved_for_conforming_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = module_for("plugins.version.provider", version="1.2.0")
    module.PROVIDER_MANIFEST = ProviderManifest(
        key="market:demo",
        name="Demo",
        version="1.2.0",
        api_major=1,
        capabilities=("market",),
    )
    install(monkeypatch, module)
    configure(
        monkeypatch,
        **{
            "market:demo": ProviderInfo(
                module=module.__name__,
                name="Demo",
                capabilities=("market",),
            )
        },
    )
    monkeypatch.setattr(plugin_loader, "API_VERSION", "1.0.0")
    plugin_loader.refresh_provider_cache()

    descriptor = plugin_loader.provider_descriptors()[0]

    assert descriptor.compatibility.status == "compatible"
    assert descriptor.version == "1.2.0"


def test_refresh_provider_cache_forces_new_descriptor_inspection(monkeypatch: pytest.MonkeyPatch) -> None:
    module = module_for("plugins.refresh.provider")
    install(monkeypatch, module)
    configure(
        monkeypatch,
        **{
            "market:demo": ProviderInfo(
                module=module.__name__,
                name="Demo",
                capabilities=("market",),
            )
        },
    )
    assert plugin_loader.provider_descriptors()[0].conformance.passed

    module.provider = None
    assert plugin_loader.provider_descriptors()[0].conformance.passed
    plugin_loader.refresh_provider_cache()
    assert not plugin_loader.provider_descriptors()[0].conformance.passed


def test_compatibility_statuses_and_reason_serialization(monkeypatch: pytest.MonkeyPatch) -> None:
    passing = plugin_loader.inspect_provider_module(module_for("plugins.compat.provider"), api_version="0.0.0")

    monkeypatch.setattr(plugin_loader, "API_VERSION", "invalid")
    unknown_api = plugin_loader._compatibility("0.3.0", passing)
    assert unknown_api.status == "unknown"
    assert unknown_api.to_dict()["reason"] == "api version is not parseable"

    monkeypatch.setattr(plugin_loader, "API_VERSION", "0.0.0")
    unknown_provider = plugin_loader._compatibility(None, passing)
    assert unknown_provider.status == "unknown"
    assert unknown_provider.reason == "provider version is not declared or parseable"

    mismatch = plugin_loader._compatibility("2.0.0", passing)
    assert mismatch.status == "incompatible"
    assert "differs" in str(mismatch.to_dict()["reason"])


def test_provider_version_reads_supported_attributes_and_missing_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = ModuleType("plugins.version_attributes.provider")
    module.VERSION = " 0.4.0 "
    install(monkeypatch, module)
    assert plugin_loader._provider_version(module.__name__) == "0.4.0"

    del module.VERSION
    module.version = ""
    assert plugin_loader._provider_version(module.__name__) is None
    assert plugin_loader._provider_version("plugins.does_not_exist.provider") is None


def test_cached_helpers_tolerate_configuration_change_after_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure(
        monkeypatch,
        **{
            "market:demo": ProviderInfo(
                module="plugins.demo.provider",
                name="Demo",
                capabilities=("market",),
            )
        },
    )
    signature = plugin_loader._provider_signature()
    plugin_loader.settings.allowed_providers.clear()

    assert plugin_loader._cached_provider_metadata(signature, None) == ()
    assert plugin_loader._cached_provider_descriptors(signature, None) == ()
