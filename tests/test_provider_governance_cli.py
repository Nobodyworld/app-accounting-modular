"""Operator CLI coverage for persistent provider governance."""

from __future__ import annotations

import json

import pytest
from cli import provider_sdk as sdk_cli
from click.testing import CliRunner
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine


@pytest.fixture()
def cli_engine(monkeypatch: pytest.MonkeyPatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(sdk_cli, "engine", engine)
    monkeypatch.setattr(sdk_cli, "init_db", lambda: None)
    try:
        yield engine
    finally:
        engine.dispose()


def test_operator_reconcile_validate_and_export_are_deterministic(cli_engine) -> None:
    runner = CliRunner()
    reconciled = runner.invoke(
        sdk_cli.provider_sdk_group,
        ["governance-reconcile", "--format", "json"],
    )
    assert reconciled.exit_code == 0, reconciled.output
    payload = json.loads(reconciled.output)
    assert payload["changed"] == sorted(payload["changed"])
    assert payload["provider_count"] > 0

    second = runner.invoke(
        sdk_cli.provider_sdk_group,
        ["governance-reconcile", "--format", "json"],
    )
    assert second.exit_code == 0, second.output
    assert json.loads(second.output)["changed"] == []

    validated = runner.invoke(
        sdk_cli.provider_sdk_group,
        ["governance-validate", "--format", "json"],
    )
    assert validated.exit_code == 0, validated.output
    assert json.loads(validated.output)["valid"] is True

    first_export = runner.invoke(
        sdk_cli.provider_sdk_group,
        ["governance-export", "--organization-id", "1", "--format", "json"],
    )
    second_export = runner.invoke(
        sdk_cli.provider_sdk_group,
        ["governance-export", "--organization-id", "1", "--format", "json"],
    )
    assert first_export.exit_code == second_export.exit_code == 0
    assert first_export.output == second_export.output
    assert "credential_env" not in first_export.output
    assert "plugins." not in first_export.output


def test_operator_commands_expose_no_tenant_module_registration_option(cli_engine) -> None:
    result = CliRunner().invoke(
        sdk_cli.provider_sdk_group,
        ["governance-reconcile", "--module", "tenant.evil.provider"],
    )
    assert result.exit_code == 2
    assert "No such option" in result.output
