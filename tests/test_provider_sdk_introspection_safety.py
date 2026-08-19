from __future__ import annotations

from types import ModuleType
from typing import Any

from apps.provider_sdk import ProviderManifest, inspect_provider_module


class CompleteTaxProvider:
    name = "complete"

    def upsert_rules(self) -> list[object]:
        return []


def make_module(*, provider_type: type[Any] = CompleteTaxProvider) -> ModuleType:
    module = ModuleType("plugins.introspection_safety.provider")
    module.__version__ = "0.3.0"
    module.PROVIDER_MANIFEST = ProviderManifest(
        key="tax:introspection_safety",
        name="Introspection Safety",
        version="0.3.0",
        api_major=0,
        capabilities=("tax",),
    )

    def provider() -> provider_type:  # type: ignore[valid-type]
        return provider_type()

    provider.__annotations__["return"] = provider_type
    module.provider = provider
    return module


def check_message(report: Any, code: str) -> str:
    return next(check.message for check in report.checks if check.code == code)


def test_structural_descriptor_lookups_are_sanitized() -> None:
    class ExplodingName:
        @property
        def name(self) -> str:
            raise RuntimeError("credential=secret-name")

        def upsert_rules(self) -> list[object]:
            return []

    class ExplodingMethod:
        name = "exploding-method"

        @property
        def upsert_rules(self) -> Any:
            raise RuntimeError("credential=secret-method")

    name_report = inspect_provider_module(
        make_module(provider_type=ExplodingName),
        expected_key="tax:introspection_safety",
        expected_capabilities=("tax",),
        api_version="0.0.0",
    )
    method_report = inspect_provider_module(
        make_module(provider_type=ExplodingMethod),
        expected_key="tax:introspection_safety",
        expected_capabilities=("tax",),
        api_version="0.0.0",
    )

    assert name_report.failure_codes == ("provider.name",)
    assert check_message(name_report, "provider.name") == "provider name lookup failed (RuntimeError)"
    assert "secret-name" not in name_report.to_json()
    assert method_report.failure_codes == ("capability.tax.upsert_rules",)
    assert "secret-method" not in method_report.to_json()


def test_factory_signature_failure_is_sanitized() -> None:
    class ExplodingFactory:
        @property
        def __signature__(self) -> Any:
            raise RuntimeError("credential=secret-signature")

        def __call__(self) -> CompleteTaxProvider:
            return CompleteTaxProvider()

    module = make_module()
    module.provider = ExplodingFactory()
    report = inspect_provider_module(
        module,
        expected_key="tax:introspection_safety",
        expected_capabilities=("tax",),
        api_version="0.0.0",
    )

    assert report.failure_codes == ("factory.signature",)
    assert "secret-signature" not in report.to_json()


def test_manifest_lookup_failure_is_sanitized() -> None:
    class ExplodingModule(ModuleType):
        def __getattribute__(self, name: str) -> Any:
            if name == "PROVIDER_MANIFEST":
                raise RuntimeError("credential=secret-manifest")
            return super().__getattribute__(name)

    module = ExplodingModule("plugins.exploding_manifest.provider")
    report = inspect_provider_module(module, api_version="0.0.0")

    assert report.failure_codes == ("manifest.present",)
    assert "secret-manifest" not in report.to_json()
