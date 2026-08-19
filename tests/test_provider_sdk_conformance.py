from __future__ import annotations

import json
from datetime import date
from types import ModuleType
from typing import Any

import pytest
from apps.provider_sdk import (
    ConformanceCheck,
    ProviderConformanceError,
    ProviderConformanceReport,
    ProviderManifest,
    inspect_provider_module,
    load_conforming_provider,
)


class CompleteProvider:
    name = "complete"

    def sync_daily_rates(self, base: str = "USD", date_: date | None = None) -> list[object]:
        raise AssertionError("data method must not run during conformance")

    def fetch_prices(self, symbol: str, start: date, end: date) -> list[object]:
        raise AssertionError("data method must not run during conformance")

    def upsert_rules(self) -> list[object]:
        raise AssertionError("data method must not run during conformance")

    def fetch_series(self, series_id: str, start: date, end: date) -> list[tuple[date, float]]:
        raise AssertionError("data method must not run during conformance")

    def list_accounts(self) -> list[dict[str, object]]:
        raise AssertionError("data method must not run during conformance")

    def fetch_transactions(
        self,
        account_id: str,
        start: date,
        end: date,
    ) -> list[dict[str, object]]:
        raise AssertionError("data method must not run during conformance")


def make_module(
    *,
    provider_type: type[Any] = CompleteProvider,
    key: str = "test:complete",
    capabilities: tuple[str, ...] = ("bank", "fx", "macro", "market", "tax"),
    api_major: int = 0,
    sdk_version: str = "1.0",
    version: str = "0.3.0",
    factory_result: Any | None = None,
) -> ModuleType:
    module = ModuleType("plugins.test_complete.provider")
    module.PROVIDER_MANIFEST = ProviderManifest(
        key=key,
        name="Complete Provider",
        version=version,
        api_major=api_major,
        capabilities=capabilities,
        sdk_version=sdk_version,
    )
    module.__version__ = version

    def provider() -> provider_type:  # type: ignore[valid-type]
        return provider_type() if factory_result is None else factory_result

    provider.__annotations__["return"] = provider_type
    module.provider = provider
    return module


def check(report: ProviderConformanceReport, code: str) -> ConformanceCheck:
    return next(item for item in report.checks if item.code == code)


def test_structural_conformance_checks_all_capabilities_without_invoking_factory_or_data() -> None:
    module = make_module()

    def forbidden_factory() -> CompleteProvider:
        raise AssertionError("factory must not be invoked")

    forbidden_factory.__annotations__["return"] = CompleteProvider
    module.provider = forbidden_factory
    report = inspect_provider_module(
        module,
        expected_key="test:complete",
        expected_capabilities=("tax", "bank", "market", "macro", "fx"),
        api_version="0.9.0",
    )

    assert report.passed, report.to_json()
    assert check(report, "factory.result").message == "factory invocation deferred to runtime loading"
    assert check(report, "capability.bank.fetch_transactions").status == "pass"
    assert check(report, "capability.fx.sync_daily_rates").status == "pass"
    assert check(report, "capability.macro.fetch_series").status == "pass"
    assert check(report, "capability.market.fetch_prices").status == "pass"
    assert check(report, "capability.tax.upsert_rules").status == "pass"


def test_runtime_loading_returns_instance_manifest_and_report() -> None:
    module = make_module(capabilities=("market",))
    loaded = load_conforming_provider(
        module,
        expected_key="test:complete",
        expected_capabilities=("market",),
        api_version="0.0.0",
    )
    assert isinstance(loaded.instance, CompleteProvider)
    assert loaded.manifest.key == "test:complete"
    assert loaded.report.passed


def test_missing_module_failure_is_sanitized() -> None:
    report = inspect_provider_module("not_a_real_provider.secret-value")
    assert not report.passed
    assert report.failure_codes == ("module.import",)
    assert "secret-value" not in check(report, "module.import").message
    assert "ModuleNotFoundError" in check(report, "module.import").message


def test_missing_manifest_fails_closed() -> None:
    report = inspect_provider_module(ModuleType("provider_without_manifest"))
    assert report.failure_codes == ("manifest.present",)


@pytest.mark.parametrize(
    ("kwargs", "expected_code"),
    [
        ({"sdk_version": "9.9"}, "manifest.sdk"),
        ({"api_major": 1}, "manifest.api"),
    ],
)
def test_manifest_compatibility_failures(kwargs: dict[str, object], expected_code: str) -> None:
    report = inspect_provider_module(make_module(**kwargs), api_version="0.0.0")
    assert expected_code in report.failure_codes


def test_invalid_application_version_fails_closed() -> None:
    report = inspect_provider_module(make_module(), api_version="not-a-version")
    assert "manifest.api" in report.failure_codes


def test_configuration_key_and_capability_drift_fail() -> None:
    report = inspect_provider_module(
        make_module(capabilities=("market",)),
        expected_key="market:different",
        expected_capabilities=("fx",),
        api_version="0.0.0",
    )
    assert report.failure_codes == ("manifest.key", "manifest.capabilities")


def test_module_and_manifest_version_drift_fails() -> None:
    module = make_module()
    module.__version__ = "0.4.0"
    report = inspect_provider_module(module, api_version="0.0.0")
    assert "manifest.version" in report.failure_codes


def test_missing_module_version_uses_manifest_authority() -> None:
    module = make_module(capabilities=("tax",))
    del module.__version__
    report = inspect_provider_module(module, api_version="0.0.0")
    assert report.passed
    assert check(report, "manifest.version").message == "manifest version is authoritative"


def test_requested_factory_must_match_manifest() -> None:
    report = inspect_provider_module(make_module(), factory_name="build", api_version="0.0.0")
    assert report.failure_codes == ("factory.manifest",)


def test_factory_must_be_callable() -> None:
    module = make_module()
    module.provider = None
    report = inspect_provider_module(module, api_version="0.0.0")
    assert report.failure_codes == ("factory.callable",)


def test_async_factory_is_rejected() -> None:
    module = make_module()

    async def provider() -> CompleteProvider:
        return CompleteProvider()

    module.provider = provider
    report = inspect_provider_module(module, api_version="0.0.0")
    assert report.failure_codes == ("factory.sync",)


def test_factory_required_arguments_are_rejected() -> None:
    module = make_module()

    def provider(required: str) -> CompleteProvider:
        return CompleteProvider()

    module.provider = provider
    report = inspect_provider_module(module, api_version="0.0.0")
    assert report.failure_codes == ("factory.signature",)


def test_factory_exception_is_sanitized() -> None:
    module = make_module(capabilities=("tax",))

    def provider() -> CompleteProvider:
        raise RuntimeError("credential=super-secret")

    module.provider = provider
    report = inspect_provider_module(module, api_version="0.0.0", instantiate=True)
    message = check(report, "factory.result").message
    assert report.failure_codes == ("factory.result",)
    assert "super-secret" not in message
    assert message == "provider factory failed (RuntimeError)"


def test_factory_returning_none_is_rejected() -> None:
    module = make_module(capabilities=("tax",), factory_result=None)

    def provider() -> None:
        return None

    module.provider = provider
    report = inspect_provider_module(module, api_version="0.0.0", instantiate=True)
    assert report.failure_codes == ("factory.result",)


def test_factory_returning_awaitable_is_rejected_without_warning() -> None:
    module = make_module(capabilities=("tax",))

    async def build() -> CompleteProvider:
        return CompleteProvider()

    def provider() -> Any:
        return build()

    module.provider = provider
    report = inspect_provider_module(module, api_version="0.0.0", instantiate=True)
    assert report.failure_codes == ("factory.result",)


def test_provider_name_is_required() -> None:
    class Nameless:
        name = ""

        def upsert_rules(self) -> list[object]:
            return []

    report = inspect_provider_module(
        make_module(provider_type=Nameless, capabilities=("tax",)),
        api_version="0.0.0",
        instantiate=True,
    )
    assert report.failure_codes == ("provider.name",)


def test_missing_method_and_incompatible_signature_fail() -> None:
    class Broken:
        name = "broken"

        def fetch_prices(self, ticker: str, start: date, end: date, required: str) -> list[object]:
            return []

    report = inspect_provider_module(
        make_module(provider_type=Broken, capabilities=("bank", "market")),
        api_version="0.0.0",
    )
    assert "capability.bank.fetch_transactions" in report.failure_codes
    assert "capability.bank.list_accounts" in report.failure_codes
    assert "capability.market.fetch_prices" in report.failure_codes


def test_missing_return_annotation_warns_but_runtime_loading_completes_checks() -> None:
    module = make_module(capabilities=("tax",))

    def provider():
        return CompleteProvider()

    module.provider = provider
    report = inspect_provider_module(module, api_version="0.0.0")
    assert report.passed
    assert check(report, "provider.structure").status == "warning"


def test_report_json_is_deterministic() -> None:
    report = inspect_provider_module(make_module(capabilities=("fx",)), api_version="0.0.0")
    assert report.to_json() == report.to_json()
    payload = json.loads(report.to_json())
    assert payload["passed"] is True
    assert payload["manifest"]["key"] == "test:complete"


def test_bounded_check_and_report_validation() -> None:
    with pytest.raises(ValueError, match="code"):
        ConformanceCheck(code="INVALID", status="pass", message="ok")
    with pytest.raises(ValueError, match="message exceeds"):
        ConformanceCheck(code="valid.code", status="pass", message="x" * 257)
    with pytest.raises(ValueError, match="module exceeds"):
        ProviderConformanceReport(module="x" * 257, checks=())


def test_load_conforming_provider_raises_with_only_stable_failure_codes() -> None:
    module = make_module(capabilities=("tax",))
    module.provider = None
    with pytest.raises(ProviderConformanceError) as exc_info:
        load_conforming_provider(
            module,
            expected_key="test:complete",
            expected_capabilities=("tax",),
            api_version="0.0.0",
        )
    assert str(exc_info.value) == "Provider conformance failed: factory.callable"
