"""Provider SDK commands for structural validation and scaffolding."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from apps.api.config import settings
from apps.api.version import API_VERSION
from apps.provider_sdk import (
    DATA_CLASSIFICATIONS,
    NETWORK_POLICIES,
    SUPPORTED_CAPABILITIES,
    ProviderConformanceReport,
    inspect_provider_module,
    scaffold_provider,
)


def _render_report(report: ProviderConformanceReport) -> str:
    rows = [(check.code, check.status.upper(), check.message) for check in report.checks]
    headers = ("Check", "Status", "Message")
    widths = [len(value) for value in headers]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    def render_row(row: tuple[str, str, str]) -> str:
        return "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))

    lines = [render_row(headers)]
    lines.append("  ".join("-" * width for width in widths))
    lines.extend(render_row(row) for row in rows)
    lines.append("")
    lines.append(f"Provider module: {report.module}")
    lines.append(f"Disposition: {'PASS' if report.passed else 'FAIL'}")
    return "\n".join(lines)


def _resolve_target(
    key: str | None,
    module: str | None,
) -> tuple[str, str | None, tuple[str, ...] | None]:
    if bool(key) == bool(module):
        raise click.UsageError("Provide exactly one of --key or --module")
    if module is not None:
        return module, None, None
    assert key is not None
    info = settings.allowed_providers.get(key)
    if info is None:
        raise click.ClickException(f"Provider '{key}' is not allowed")
    return info.module, key, tuple(info.capabilities)


@click.group("provider-sdk")
def provider_sdk_group() -> None:
    """Validate and scaffold provider adapter packages."""


@provider_sdk_group.command("validate")
@click.option("--key", help="Configured provider key to validate.")
@click.option("--module", help="Importable provider module to validate.")
@click.option(
    "--format",
    "format_",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
    show_default=True,
)
@click.option(
    "--instantiate/--structural-only",
    default=False,
    help="Invoke the synchronous factory after structural checks.",
)
def validate_provider(
    key: str | None,
    module: str | None,
    format_: str,
    instantiate: bool,
) -> None:
    """Emit deterministic provider conformance evidence."""

    target, expected_key, expected_capabilities = _resolve_target(key, module)
    report = inspect_provider_module(
        target,
        expected_key=expected_key,
        expected_capabilities=expected_capabilities,
        api_version=API_VERSION,
        instantiate=instantiate,
    )
    if format_.lower() == "json":
        click.echo(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        click.echo(_render_report(report))
    if not report.passed:
        raise click.exceptions.Exit(1)


@provider_sdk_group.command("scaffold")
@click.argument("key")
@click.option(
    "--capability",
    "capabilities",
    type=click.Choice(SUPPORTED_CAPABILITIES, case_sensitive=True),
    multiple=True,
    required=True,
)
@click.option(
    "--directory",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("src/plugins"),
    show_default=True,
)
@click.option("--name")
@click.option("--version", default="0.1.0", show_default=True)
@click.option("--api-major", type=click.IntRange(0, 999), default=0, show_default=True)
@click.option("--description")
@click.option("--homepage")
@click.option("--license", "license_name")
@click.option(
    "--network-policy",
    type=click.Choice(NETWORK_POLICIES, case_sensitive=True),
    default="none",
    show_default=True,
)
@click.option("--credential-env", multiple=True)
@click.option(
    "--data-classification",
    type=click.Choice(DATA_CLASSIFICATIONS, case_sensitive=True),
    default="controlled-sample",
    show_default=True,
)
@click.option("--force", is_flag=True, help="Overwrite only the known generated files.")
def scaffold_provider_command(
    key: str,
    capabilities: tuple[str, ...],
    directory: Path,
    name: str | None,
    version: str,
    api_major: int,
    description: str | None,
    homepage: str | None,
    license_name: str | None,
    network_policy: str,
    credential_env: tuple[str, ...],
    data_classification: str,
    force: bool,
) -> None:
    """Generate a provider package and its structural conformance test."""

    try:
        result = scaffold_provider(
            directory,
            key=key,
            capabilities=capabilities,
            name=name,
            version=version,
            api_major=api_major,
            description=description,
            homepage=homepage,
            license=license_name,
            network_policy=network_policy,
            credential_env=credential_env,
            data_classification=data_classification,
            force=force,
        )
    except (FileExistsError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    payload: dict[str, Any] = {
        "key": result.key,
        "package": result.package,
        "root": str(result.root),
        "created_files": [str(path) for path in result.created_files],
    }
    click.echo(json.dumps(payload, indent=2, sort_keys=True))
