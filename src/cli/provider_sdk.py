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


def _resolve_targets(
    key: str | None,
    module: str | None,
    all_configured: bool,
) -> tuple[tuple[str, str | None, tuple[str, ...] | None], ...]:
    selected = sum((key is not None, module is not None, all_configured))
    if selected != 1:
        raise click.UsageError("Provide exactly one of --key, --module, or --all-configured")
    if module is not None:
        return ((module, None, None),)
    if key is not None:
        info = settings.allowed_providers.get(key)
        if info is None:
            raise click.ClickException(f"Provider '{key}' is not allowed")
        return ((info.module, key, tuple(info.capabilities)),)
    return tuple(
        (info.module, provider_key, tuple(info.capabilities))
        for provider_key, info in sorted(settings.allowed_providers.items())
    )


def _render_reports(reports: tuple[ProviderConformanceReport, ...]) -> str:
    return "\n\n".join(_render_report(report) for report in reports)


def _json_reports(reports: tuple[ProviderConformanceReport, ...]) -> dict[str, Any] | dict[str, object]:
    if len(reports) == 1:
        return reports[0].to_dict()
    return {
        "passed": all(report.passed for report in reports),
        "provider_count": len(reports),
        "reports": [report.to_dict() for report in reports],
    }


@click.group("provider-sdk")
def provider_sdk_group() -> None:
    """Validate and scaffold provider adapter packages."""


@provider_sdk_group.command("validate")
@click.option("--key", help="Configured provider key to validate.")
@click.option("--module", help="Importable provider module to validate.")
@click.option("--all-configured", is_flag=True, help="Validate every configured provider.")
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
    help="Invoke synchronous factories after structural checks.",
)
def validate_provider(
    key: str | None,
    module: str | None,
    all_configured: bool,
    format_: str,
    instantiate: bool,
) -> None:
    """Emit deterministic provider conformance evidence."""

    targets = _resolve_targets(key, module, all_configured)
    reports = tuple(
        inspect_provider_module(
            target,
            expected_key=expected_key,
            expected_capabilities=expected_capabilities,
            api_version=API_VERSION,
            instantiate=instantiate,
        )
        for target, expected_key, expected_capabilities in targets
    )
    if format_.lower() == "json":
        click.echo(json.dumps(_json_reports(reports), indent=2, sort_keys=True))
    else:
        click.echo(_render_reports(reports))
    if not all(report.passed for report in reports):
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
@click.option(
    "--format",
    "format_",
    type=click.Choice(["table", "json"], case_sensitive=False),
    default="table",
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
    format_: str,
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

    relative_files = tuple(path.relative_to(directory) for path in result.created_files)
    payload: dict[str, Any] = {
        "key": result.key,
        "package": result.package,
        "module": result.module,
        "root": result.package,
        "created_files": [path.as_posix() for path in relative_files],
    }
    if format_.lower() == "json":
        click.echo(json.dumps(payload, indent=2, sort_keys=True))
        return

    click.echo(f"Scaffolded provider: {result.key}")
    click.echo(f"Import module: {result.module}")
    click.echo("Generated files:")
    for path in relative_files:
        click.echo(f"- {path.as_posix()}")


if __name__ == "__main__":  # pragma: no cover - manual invocation guard
    provider_sdk_group()
