"""Deterministic scaffolding for third-party provider packages."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import cast

from .contracts import DataClassification, NetworkPolicy, ProviderManifest

__all__ = [
    "ProviderProjectScaffold",
    "ProviderScaffold",
    "normalise_distribution_name",
    "normalise_provider_package",
    "scaffold_project",
    "scaffold_provider",
]

_PACKAGE_PATTERN = re.compile(r"^[a-z_][a-z0-9_]*$")
_DISTRIBUTION_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True, slots=True)
class ProviderScaffold:
    """Metadata describing generated provider package files."""

    key: str
    package: str
    module: str
    root: Path
    created_files: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class ProviderProjectScaffold:
    """Metadata describing a standalone, conventionally packaged project."""

    key: str
    distribution: str
    package: str
    module: str
    root: Path
    created_files: tuple[Path, ...]


def normalise_provider_package(key: str) -> str:
    """Return a Python package name derived from a provider key."""

    package = key.replace(":", "_").replace("-", "_")
    if _PACKAGE_PATTERN.fullmatch(package) is None:
        raise ValueError("Provider key does not produce a safe Python package name")
    return package


def normalise_distribution_name(value: str) -> str:
    """Return a bounded normalized Python distribution name."""

    distribution = value.strip().lower().replace("_", "-")
    if len(distribution) > 96 or _DISTRIBUTION_PATTERN.fullmatch(distribution) is None:
        raise ValueError("Distribution name must use lowercase letters, numbers, and single hyphens")
    return distribution


def _literal(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _tuple_literal(values: Iterable[str]) -> str:
    items = tuple(values)
    if not items:
        return "()"
    return "(" + ", ".join(_literal(value) for value in items) + ",)"


def _method_lines(capability: str) -> list[str]:
    if capability == "fx":
        return [
            '    def sync_daily_rates(self, base: str = "USD", date_: date | None = None) -> list[object]:',
            '        """Return provider-specific FX records after implementing the adapter."""',
            "",
            "        return []",
        ]
    if capability == "market":
        return [
            "    def fetch_prices(self, symbol: str, start: date, end: date) -> list[object]:",
            '        """Return provider-specific market records after implementing the adapter."""',
            "",
            "        return []",
        ]
    if capability == "tax":
        return [
            "    def upsert_rules(self) -> list[object]:",
            '        """Return provider-specific tax rules after implementing the adapter."""',
            "",
            "        return []",
        ]
    if capability == "macro":
        return [
            "    def fetch_series(self, series_id: str, start: date, end: date) -> list[tuple[date, float]]:",
            '        """Return provider-specific macro observations after implementing the adapter."""',
            "",
            "        return []",
        ]
    if capability == "bank":
        return [
            "    def list_accounts(self) -> list[dict[str, object]]:",
            '        """Return provider-specific account summaries after implementing the adapter."""',
            "",
            "        return []",
            "",
            "    def fetch_transactions(",
            "        self,",
            "        account_id: str,",
            "        start: date,",
            "        end: date,",
            "    ) -> list[dict[str, object]]:",
            '        """Return provider-specific bank transactions after implementing the adapter."""',
            "",
            "        return []",
        ]
    raise ValueError(f"Unsupported provider capability: {capability}")


def _provider_source(
    manifest: ProviderManifest,
    class_name: str,
    *,
    sdk_import: str = "apps.provider_sdk",
    generated_by: str = "python -m cli.macli provider-sdk scaffold",
) -> str:
    manifest_lines = [
        "PROVIDER_MANIFEST = ProviderManifest(",
        f"    key={_literal(manifest.key)},",
        f"    name={_literal(manifest.name)},",
        f"    version={_literal(manifest.version)},",
        f"    api_major={manifest.api_major},",
        f"    capabilities={_tuple_literal(manifest.capabilities)},",
        f"    factory={_literal(manifest.factory)},",
        f"    sdk_version={_literal(manifest.sdk_version)},",
    ]
    if manifest.description is not None:
        manifest_lines.append(f"    description={_literal(manifest.description)},")
    if manifest.homepage is not None:
        manifest_lines.append(f"    homepage={_literal(manifest.homepage)},")
    if manifest.license is not None:
        manifest_lines.append(f"    license={_literal(manifest.license)},")
    manifest_lines.extend(
        [
            f"    network_policy={_literal(manifest.network_policy)},",
            f"    credential_env={_tuple_literal(manifest.credential_env)},",
            f"    data_classification={_literal(manifest.data_classification)},",
            ")",
        ]
    )

    lines = [
        f'"""Provider package generated by `{generated_by}`."""',
        "",
        "from __future__ import annotations",
        "",
        "from datetime import date",
        "",
        f"from {sdk_import} import ProviderManifest",
        "",
        f'__version__ = "{manifest.version}"',
        "",
        *manifest_lines,
        "",
        "",
        f"class {class_name}:",
        f'    """Starter implementation for {manifest.name}."""',
        "",
        f"    name = {_literal(manifest.name)}",
    ]
    for capability in manifest.capabilities:
        lines.extend(["", *_method_lines(capability)])
    lines.extend(
        [
            "",
            "",
            f"def provider() -> {class_name}:",
            '    """Return the synchronous provider instance."""',
            "",
            f"    return {class_name}()",
            "",
        ]
    )
    return "\n".join(lines)


def _module_name(directory: Path, package: str) -> str:
    prefix = "plugins." if directory.name == "plugins" else ""
    return f"{prefix}{package}.provider"


def scaffold_provider(
    directory: Path,
    *,
    key: str,
    capabilities: Iterable[str],
    name: str | None = None,
    version: str = "0.1.0",
    api_major: int = 0,
    description: str | None = None,
    homepage: str | None = None,
    license: str | None = None,
    network_policy: str = "none",
    credential_env: Iterable[str] = (),
    data_classification: str = "controlled-sample",
    force: bool = False,
) -> ProviderScaffold:
    """Create a deterministic provider package and conformance test."""

    manifest = ProviderManifest(
        key=key,
        name=name or key.split(":", 1)[-1].replace("-", " ").replace("_", " ").title(),
        version=version,
        api_major=api_major,
        capabilities=tuple(capabilities),
        description=description,
        homepage=homepage,
        license=license,
        network_policy=cast(NetworkPolicy, network_policy),
        credential_env=tuple(credential_env),
        data_classification=cast(DataClassification, data_classification),
    )
    package = normalise_provider_package(manifest.key)
    module = _module_name(directory, package)
    target = directory / package
    known_paths = (
        target / "__init__.py",
        target / "provider.py",
        target / "README.md",
        target / "tests" / "test_conformance.py",
    )
    existing = tuple(path for path in known_paths if path.exists())
    if existing and not force:
        raise FileExistsError(f"Provider package '{package}' already contains generated files")

    (target / "tests").mkdir(parents=True, exist_ok=True)
    class_name = "".join(part.capitalize() for part in package.split("_")) + "Provider"

    init_source = dedent(
        '''\
        """Generated provider package."""

        from .provider import PROVIDER_MANIFEST, provider

        __all__ = ["PROVIDER_MANIFEST", "provider"]
        '''
    ).lstrip()
    provider_source = _provider_source(manifest, class_name)
    readme_source = dedent(
        f"""\
        # {manifest.name}

        Generated with `python -m cli.macli provider-sdk scaffold`.

        - Provider key: `{manifest.key}`
        - Import module: `{module}`
        - SDK version: `{manifest.sdk_version}`
        - Implementation version: `{manifest.version}`
        - Capabilities: `{", ".join(manifest.capabilities)}`
        - Network policy: `{manifest.network_policy}`
        - Credential environment variables: `{", ".join(manifest.credential_env) or "none"}`

        The generated implementation is intentionally non-networked and returns
        empty result collections. Replace those method bodies with bounded,
        sanitized adapter logic and retain the conformance test.
        """
    ).lstrip()
    test_source = dedent(
        f'''\
        from apps.api.version import API_VERSION
        from apps.provider_sdk import inspect_provider_module

        MODULE = "{module}"


        def test_generated_provider_conforms() -> None:
            report = inspect_provider_module(
                MODULE,
                expected_key="{manifest.key}",
                expected_capabilities={manifest.capabilities!r},
                api_version=API_VERSION,
            )

            assert report.passed, report.to_json()
        '''
    ).lstrip()

    contents = (init_source, provider_source, readme_source, test_source)
    for path, content in zip(known_paths, contents, strict=True):
        path.write_text(content, encoding="utf-8", newline="\n")

    return ProviderScaffold(
        key=manifest.key,
        package=package,
        module=module,
        root=target,
        created_files=known_paths,
    )


def scaffold_project(
    directory: Path,
    *,
    key: str,
    capabilities: Iterable[str],
    distribution: str | None = None,
    package: str | None = None,
    name: str | None = None,
    version: str = "0.1.0",
    api_major: int = 0,
    description: str | None = None,
    homepage: str | None = None,
    license: str | None = None,
    network_policy: str = "none",
    credential_env: Iterable[str] = (),
    data_classification: str = "controlled-sample",
    force: bool = False,
) -> ProviderProjectScaffold:
    """Generate a standalone provider project without authorizing it in an application."""

    manifest = ProviderManifest(
        key=key,
        name=name or key.split(":", 1)[-1].replace("-", " ").replace("_", " ").title(),
        version=version,
        api_major=api_major,
        capabilities=tuple(capabilities),
        description=description,
        homepage=homepage,
        license=license,
        network_policy=cast(NetworkPolicy, network_policy),
        credential_env=tuple(credential_env),
        data_classification=cast(DataClassification, data_classification),
    )
    package_name = package or normalise_provider_package(manifest.key)
    if _PACKAGE_PATTERN.fullmatch(package_name) is None or len(package_name) > 96:
        raise ValueError("Package name must be a safe lowercase Python import name")
    distribution_name = normalise_distribution_name(distribution or package_name.replace("_", "-"))
    project_root = directory / distribution_name
    source_root = project_root / "src" / package_name
    known_paths = (
        project_root / "pyproject.toml",
        project_root / "README.md",
        source_root / "__init__.py",
        source_root / "provider.py",
        source_root / "py.typed",
        project_root / "tests" / "test_conformance.py",
    )
    if any(path.exists() for path in known_paths) and not force:
        raise FileExistsError(f"Provider project '{distribution_name}' already contains generated files")

    (project_root / "tests").mkdir(parents=True, exist_ok=True)
    source_root.mkdir(parents=True, exist_ok=True)
    class_name = "".join(part.capitalize() for part in package_name.split("_")) + "Provider"
    module = f"{package_name}.provider"
    pyproject_source = dedent(
        f"""\
        [build-system]
        requires = []
        build-backend = "modular_accounting_provider_sdk.build_backend"

        [project]
        name = "{distribution_name}"
        version = "{manifest.version}"
        description = {_literal(manifest.description or manifest.name)}
        readme = "README.md"
        requires-python = ">=3.12"
        dependencies = ["modular-accounting-provider-sdk==0.5.0"]

        [tool.modular-accounting-provider]
        key = "{manifest.key}"
        module = "{module}"
        sdk-contract = "{manifest.sdk_version}"
        api-major = {manifest.api_major}
        scaffold-version = "0.5.0"
        capabilities = {list(manifest.capabilities)!r}
        """
    ).lstrip()
    init_source = dedent(
        f"""\
        \"\"\"{manifest.name} provider package.\"\"\"

        from .provider import PROVIDER_MANIFEST, provider

        __version__ = "{manifest.version}"
        __all__ = ["PROVIDER_MANIFEST", "provider"]
        """
    ).lstrip()
    provider_source = _provider_source(
        manifest,
        class_name,
        sdk_import="modular_accounting_provider_sdk",
        generated_by="python -m modular_accounting_provider_sdk scaffold",
    )
    readme_source = dedent(
        f"""\
        # {manifest.name}

        Standalone provider scaffold for `{manifest.key}`.

        - Distribution: `{distribution_name}`
        - Import module: `{module}`
        - SDK contract: `{manifest.sdk_version}`
        - Application API major: `{manifest.api_major}`
        - Capabilities: `{", ".join(manifest.capabilities)}`

        Installation and importability do not authorize execution. An operator must
        explicitly add the exact key, module, and capabilities to the application's
        trusted allowlist before v0.4 reconciliation and organization policy apply.
        The generated data methods are non-networked placeholders.
        """
    ).lstrip()
    test_source = dedent(
        f"""\
        import unittest

        from modular_accounting_provider_sdk import inspect_provider_module


        class ProviderConformanceTest(unittest.TestCase):
            def test_generated_provider_conforms_without_data_calls(self) -> None:
                report = inspect_provider_module(
                    "{module}",
                    expected_key="{manifest.key}",
                    expected_capabilities={manifest.capabilities!r},
                    api_version="{manifest.api_major}.0.0",
                )
                self.assertTrue(report.passed, report.to_json())


        if __name__ == "__main__":
            unittest.main()
        """
    ).lstrip()
    contents = (pyproject_source, readme_source, init_source, provider_source, "", test_source)
    for path, content in zip(known_paths, contents, strict=True):
        path.write_text(content, encoding="utf-8", newline="\n")
    return ProviderProjectScaffold(
        key=manifest.key,
        distribution=distribution_name,
        package=package_name,
        module=module,
        root=project_root,
        created_files=known_paths,
    )
