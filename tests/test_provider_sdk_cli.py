from __future__ import annotations

import json
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from click.testing import CliRunner

from apps.api.config import ProviderInfo
from apps.provider_sdk import ProviderManifest
from cli import provider_sdk as sdk_cli


class TaxProvider:
    name = "tax"

    def upsert_rules(self) -> list[object]:
        return []


def conforming_module(name: str = "plugins.cli_test.provider") -> ModuleType:
    module = ModuleType(name)
    module.__version__ = "0.3.0"
    module.PROVIDER_MANIFEST = ProviderManifest(
        key="tax:cli_test",
        name="CLI Test",
        version="0.3.0",
        api_major=0,
        capabilities=("tax",),
    )

    def provider() -> TaxProvider:
        return TaxProvider()

    provider.__annotations__["return"] = TaxProvider
    module.provider = provider
    return module


def configure(monkeypatch: pytest.MonkeyPatch, **providers: ProviderInfo) -> None:
    monkeypatch.setattr(sdk_cli, "settings", SimpleNamespace(allowed_providers=providers))


def test_validate_requires_exactly_one_target() -> None:
    runner = CliRunner()
    neither = runner.invoke(sdk_cli.provider_sdk_group, ["validate"])
    multiple = runner.invoke(
        sdk_cli.provider_sdk_group,
        ["validate", "--key", "tax:cli_test", "--module", "plugins.cli_test.provider"],
    )
    assert neither.exit_code == 2
    assert multiple.exit_code == 2
    assert "exactly one" in neither.output


def test_validate_unknown_configured_key_is_controlled(monkeypatch: pytest.MonkeyPatch) -> None:
    configure(monkeypatch)
    result = CliRunner().invoke(sdk_cli.provider_sdk_group, ["validate", "--key", "tax:missing"])
    assert result.exit_code == 1
    assert "is not allowed" in result.output


def test_validate_configured_key_table_and_json(monkeypatch: pytest.MonkeyPatch) -> None:
    module = conforming_module()
    configure(
        monkeypatch,
        **{
            "tax:cli_test": ProviderInfo(
                module=module.__name__,
                name="CLI Test",
                capabilities=("tax",),
            )
        },
    )
    original = sdk_cli.inspect_provider_module
    monkeypatch.setattr(
        sdk_cli,
        "inspect_provider_module",
        lambda *args, **kwargs: original(module, **kwargs),
    )

    table = CliRunner().invoke(sdk_cli.provider_sdk_group, ["validate", "--key", "tax:cli_test"])
    payload = CliRunner().invoke(
        sdk_cli.provider_sdk_group,
        ["validate", "--key", "tax:cli_test", "--format", "json"],
    )

    assert table.exit_code == 0, table.output
    assert "Disposition: PASS" in table.output
    assert payload.exit_code == 0
    assert json.loads(payload.output)["manifest"]["key"] == "tax:cli_test"


def test_validate_all_configured_is_sorted_and_aggregated(monkeypatch: pytest.MonkeyPatch) -> None:
    first = conforming_module("plugins.a.provider")
    second = conforming_module("plugins.b.provider")
    first.PROVIDER_MANIFEST = ProviderManifest(
        key="tax:a", name="A", version="0.3.0", api_major=0, capabilities=("tax",)
    )
    second.PROVIDER_MANIFEST = ProviderManifest(
        key="tax:b", name="B", version="0.3.0", api_major=0, capabilities=("tax",)
    )
    modules = {first.__name__: first, second.__name__: second}
    configure(
        monkeypatch,
        **{
            "tax:b": ProviderInfo(module=second.__name__, name="B", capabilities=("tax",)),
            "tax:a": ProviderInfo(module=first.__name__, name="A", capabilities=("tax",)),
        },
    )
    original = sdk_cli.inspect_provider_module
    monkeypatch.setattr(
        sdk_cli,
        "inspect_provider_module",
        lambda target, **kwargs: original(modules[target], **kwargs),
    )

    result = CliRunner().invoke(
        sdk_cli.provider_sdk_group,
        ["validate", "--all-configured", "--format", "json"],
    )
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert payload["passed"] is True
    assert payload["provider_count"] == 2
    assert [item["manifest"]["key"] for item in payload["reports"]] == ["tax:a", "tax:b"]


def test_validate_failure_returns_exit_one_without_exception_text(monkeypatch: pytest.MonkeyPatch) -> None:
    module = conforming_module()
    module.provider = None
    original = sdk_cli.inspect_provider_module
    monkeypatch.setattr(
        sdk_cli,
        "inspect_provider_module",
        lambda target, **kwargs: original(module, **kwargs),
    )

    result = CliRunner().invoke(
        sdk_cli.provider_sdk_group,
        ["validate", "--module", module.__name__, "--format", "json"],
    )
    payload = json.loads(result.output)

    assert result.exit_code == 1
    assert payload["passed"] is False
    assert "factory.callable" in [item["code"] for item in payload["checks"]]


def test_scaffold_json_uses_relative_paths(tmp_path: Path) -> None:
    directory = tmp_path / "plugins"
    result = CliRunner().invoke(
        sdk_cli.provider_sdk_group,
        [
            "scaffold",
            "tax:cli_sample",
            "--capability",
            "tax",
            "--directory",
            str(directory),
            "--format",
            "json",
        ],
    )
    payload = json.loads(result.output)

    assert result.exit_code == 0
    assert payload["root"] == "tax_cli_sample"
    assert payload["module"] == "plugins.tax_cli_sample.provider"
    assert str(tmp_path) not in result.output
    assert payload["created_files"] == [
        "tax_cli_sample/__init__.py",
        "tax_cli_sample/provider.py",
        "tax_cli_sample/README.md",
        "tax_cli_sample/tests/test_conformance.py",
    ]


def test_scaffold_table_and_overwrite_error(tmp_path: Path) -> None:
    args = [
        "scaffold",
        "fx:cli_sample",
        "--capability",
        "fx",
        "--directory",
        str(tmp_path / "plugins"),
    ]
    runner = CliRunner()
    first = runner.invoke(sdk_cli.provider_sdk_group, args)
    second = runner.invoke(sdk_cli.provider_sdk_group, args)

    assert first.exit_code == 0
    assert "Scaffolded provider: fx:cli_sample" in first.output
    assert second.exit_code == 1
    assert "already contains generated files" in second.output
