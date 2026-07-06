from __future__ import annotations

import json
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from apps.api.config import ExtensionInfo
from apps.api.services import extension_loader
from cli.macli import cli
from click.testing import CliRunner


@pytest.fixture(autouse=True)
def clear_extension_registry() -> Iterator[None]:
    from apps.extensions import extension_registry

    extension_registry.clear()
    yield
    extension_registry.clear()


def _fake_settings(**entries: ExtensionInfo) -> SimpleNamespace:
    return SimpleNamespace(allowed_extensions=entries)


def test_inspect_extensions_table(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_extensions = {
        "observability:demo": ExtensionInfo(
            module="plugins.analytics_baseline.extension",
            description="Demo",
            enabled=True,
        )
    }
    monkeypatch.setattr(extension_loader, "settings", _fake_settings(**fake_extensions))

    runner = CliRunner()
    result = runner.invoke(cli, ["inspect-extensions"])

    assert result.exit_code == 0
    assert "observability:demo" in result.output
    assert "Baseline Observability" in result.output


def test_inspect_extensions_json(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_extensions = {
        "reporting:cashflow": ExtensionInfo(
            module="plugins.reference_cashflow.extension",
            description="Cashflow",
            enabled=False,
        )
    }
    monkeypatch.setattr(extension_loader, "settings", _fake_settings(**fake_extensions))

    runner = CliRunner()
    result = runner.invoke(cli, ["inspect-extensions", "--format", "json"])

    assert result.exit_code == 0
    lines = [line for line in result.output.splitlines() if line.strip()]
    start = next(idx for idx, line in enumerate(lines) if line.startswith("["))
    payload = json.loads("\n".join(lines[start:]))
    assert payload == [
        {
            "Capabilities": "-",
            "Enabled": "no",
            "Key": "reporting:cashflow",
            "Loaded": "no",
            "Module": "plugins.reference_cashflow.extension",
            "Name": "-",
            "Version": "-",
        }
    ]


def test_inspect_extensions_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extension_loader, "settings", _fake_settings())

    runner = CliRunner()
    result = runner.invoke(cli, ["inspect-extensions"])

    assert result.exit_code == 0
    lines = [line for line in result.output.splitlines() if line.strip()]
    assert lines[-1] == "No extensions configured."


def test_inspect_contracts_table(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_extensions = {
        "scenarios:variance": ExtensionInfo(
            module="plugins.scenario_variance.extension",
            description="Variance",
            enabled=True,
        )
    }
    monkeypatch.setattr(extension_loader, "settings", _fake_settings(**fake_extensions))

    runner = CliRunner()
    result = runner.invoke(cli, ["inspect-contracts"])

    assert result.exit_code == 0
    assert "scenarios:variance" in result.output
    assert "Base currency variance" in result.output


def test_inspect_contracts_json(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_extensions = {
        "scenarios:variance": ExtensionInfo(
            module="plugins.scenario_variance.extension",
            description="Variance",
            enabled=True,
        )
    }
    monkeypatch.setattr(extension_loader, "settings", _fake_settings(**fake_extensions))

    runner = CliRunner()
    result = runner.invoke(cli, ["inspect-contracts", "--format", "json"])

    assert result.exit_code == 0
    lines = [line for line in result.output.splitlines() if line.strip()]
    start = next(idx for idx, line in enumerate(lines) if line.startswith("["))
    payload = json.loads("\n".join(lines[start:]))
    assert payload[0]["key"] == "scenarios:variance"
    assert payload[0]["contracts"][0]["kind"] == "scenario-augmentation"
