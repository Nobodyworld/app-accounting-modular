"""Standard-library command line interface for standalone provider authors."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .build_backend import build_project_sdist, build_project_wheel
from .conformance import ProviderConformanceReport, inspect_provider_module
from .contracts import DATA_CLASSIFICATIONS, NETWORK_POLICIES, SUPPORTED_CAPABILITIES
from .evidence import artifact_evidence
from .scaffold import scaffold_project


def _table(report: ProviderConformanceReport) -> str:
    rows = [(item.code, item.status.upper(), item.message) for item in report.checks]
    headers = ("Check", "Status", "Message")
    widths = [len(value) for value in headers]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    def render(row: tuple[str, str, str]) -> str:
        return "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))

    lines = [render(headers), "  ".join("-" * width for width in widths), *(render(row) for row in rows)]
    lines.extend(("", f"Provider module: {report.module}", f"Disposition: {'PASS' if report.passed else 'FAIL'}"))
    return "\n".join(lines)


def _emit(payload: dict[str, Any], *, format_: str, report: ProviderConformanceReport | None = None) -> None:
    if format_ == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif report is not None:
        print(_table(report))
    else:
        for key in sorted(payload):
            value = payload[key]
            if isinstance(value, list):
                value = ", ".join(str(item) for item in value) or "-"
            print(f"{key.replace('_', ' ').title()}: {value}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m modular_accounting_provider_sdk")
    parser.add_argument("--version", action="version", version="%(prog)s 0.5.0")
    commands = parser.add_subparsers(dest="command", required=True)

    scaffold = commands.add_parser("scaffold", help="Generate a standalone provider project.")
    scaffold.add_argument("key")
    scaffold.add_argument("--capability", action="append", choices=SUPPORTED_CAPABILITIES, required=True)
    scaffold.add_argument("--directory", type=Path, default=Path("."))
    scaffold.add_argument("--distribution")
    scaffold.add_argument("--package")
    scaffold.add_argument("--name")
    scaffold.add_argument("--provider-version", default="0.1.0")
    scaffold.add_argument("--api-major", type=int, default=0)
    scaffold.add_argument("--description")
    scaffold.add_argument("--homepage")
    scaffold.add_argument("--license")
    scaffold.add_argument("--network-policy", choices=NETWORK_POLICIES, default="none")
    scaffold.add_argument("--credential-env", action="append", default=[])
    scaffold.add_argument("--data-classification", choices=DATA_CLASSIFICATIONS, default="controlled-sample")
    scaffold.add_argument("--force", action="store_true")
    scaffold.add_argument("--format", choices=("table", "json"), default="table")

    validate = commands.add_parser("validate", help="Run deterministic structural conformance.")
    validate.add_argument("module")
    validate.add_argument("--expected-key")
    validate.add_argument("--capability", action="append", choices=SUPPORTED_CAPABILITIES)
    validate.add_argument("--api-version", required=True)
    validate.add_argument("--factory")
    validate.add_argument("--instantiate", action="store_true")
    validate.add_argument("--format", choices=("table", "json"), default="table")

    build = commands.add_parser("build", help="Build a generated provider wheel and sdist offline.")
    build.add_argument("project", type=Path)
    build.add_argument("--output-directory", type=Path, default=Path("dist"))
    build.add_argument("--format", choices=("table", "json"), default="table")
    return parser


def _scaffold(args: argparse.Namespace) -> int:
    result = scaffold_project(
        args.directory,
        key=args.key,
        capabilities=args.capability,
        distribution=args.distribution,
        package=args.package,
        name=args.name,
        version=args.provider_version,
        api_major=args.api_major,
        description=args.description,
        homepage=args.homepage,
        license=args.license,
        network_policy=args.network_policy,
        credential_env=args.credential_env,
        data_classification=args.data_classification,
        force=args.force,
    )
    payload = {
        "created_files": [path.relative_to(result.root).as_posix() for path in result.created_files],
        "distribution": result.distribution,
        "key": result.key,
        "module": result.module,
        "package": result.package,
    }
    _emit(payload, format_=args.format)
    return 0


def _validate(args: argparse.Namespace) -> int:
    capabilities = tuple(args.capability) if args.capability else None
    report = inspect_provider_module(
        args.module,
        expected_key=args.expected_key,
        expected_capabilities=capabilities,
        api_version=args.api_version,
        instantiate=args.instantiate,
        factory_name=args.factory,
    )
    _emit(report.to_dict(), format_=args.format, report=report)
    return 0 if report.passed else 1


def _build(args: argparse.Namespace) -> int:
    root = args.project.resolve()
    output = args.output_directory
    if not output.is_absolute():
        output = root / output
    artifacts = (build_project_wheel(root, output), build_project_sdist(root, output))
    payload = {"artifacts": [artifact_evidence(path).to_dict() for path in artifacts]}
    _emit(payload, format_=args.format)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the author CLI with stable exit codes and sanitized failures."""

    args = _parser().parse_args(argv)
    try:
        if args.command == "scaffold":
            return _scaffold(args)
        if args.command == "validate":
            return _validate(args)
        if args.command == "build":
            return _build(args)
    except (FileExistsError, OSError, ValueError) as exc:
        message = str(exc).strip()
        if len(message) > 256:
            message = message[:253] + "..."
        print(f"error: {message or type(exc).__name__}", file=sys.stderr)
        return 2
    return 2
