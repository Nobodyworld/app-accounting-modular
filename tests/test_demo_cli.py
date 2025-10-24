"""Tests for the demo CLI UX improvements."""

from __future__ import annotations

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
