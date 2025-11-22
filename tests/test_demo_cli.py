"""Tests for the demo CLI UX improvements."""

from __future__ import annotations

import json

from click.testing import CliRunner

from cli.demo_cli import demo


def test_snapshot_command_table_output() -> None:
    """Table output should include labelled sections for each data type."""

    runner = CliRunner()
    result = runner.invoke(demo, ["snapshot", "--format", "table"])

    assert result.exit_code == 0
    assert "FX Rates" in result.stdout
    assert "Commodity Quotes" in result.stdout
    assert "Tax Rules" in result.stdout


def test_snapshot_command_rejects_blank_base_currency() -> None:
    """Invalid base currency should yield a helpful validation error."""

    runner = CliRunner()
    result = runner.invoke(demo, ["snapshot", "--base", "   "], catch_exceptions=False)

    assert result.exit_code != 0
    assert "base" in result.output.lower()


def test_snapshot_command_emits_diagnostics_json() -> None:
    """Diagnostics flag should include the computed diagnostics payload."""

    runner = CliRunner()
    result = runner.invoke(
        demo,
        [
            "snapshot",
            "--format",
            "json",
            "--include-diagnostics",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["diagnostics"]["fx_rate_count"] >= 1
    assert payload["diagnostics"]["missing_sections"] == []


def test_snapshot_command_emits_diagnostics_table() -> None:
    """Table output should list diagnostics when requested."""

    runner = CliRunner()
    result = runner.invoke(
        demo,
        ["snapshot", "--format", "table", "--include-diagnostics"],
    )

    assert result.exit_code == 0
    assert "Diagnostics" in result.output
    assert "Missing sections" in result.output


def test_snapshot_command_reports_missing_sections_for_unknown_commodities() -> None:
    """Diagnostics should flag missing commodities when symbols are unknown."""

    runner = CliRunner()
    result = runner.invoke(
        demo,
        [
            "snapshot",
            "--format",
            "json",
            "--include-diagnostics",
            "--commodity",
            "XYZ",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    diagnostics = payload["diagnostics"]
    assert diagnostics["commodity_quote_count"] == 0
    assert "commodities" in diagnostics["missing_sections"]
