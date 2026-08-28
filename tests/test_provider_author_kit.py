from __future__ import annotations

import ast
import importlib.util
import json
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest
from apps import provider_sdk as app_sdk
from apps.api.services import plugin_loader

from modular_accounting_provider_sdk import (
    PROVIDER_SDK_VERSION,
    ProviderManifest,
    artifact_evidence,
    build_backend,
    check_compatibility,
    scaffold_project,
)
from modular_accounting_provider_sdk import cli as standalone_cli
from modular_accounting_provider_sdk import contracts as standalone_contracts
from modular_accounting_provider_sdk.build_backend import (
    build_project_sdist,
    build_project_wheel,
    build_sdist,
    build_sdk_sdist,
    build_sdk_wheel,
    build_wheel,
    get_requires_for_build_sdist,
    get_requires_for_build_wheel,
)
from modular_accounting_provider_sdk.cli import main


def test_application_facade_preserves_public_type_identity() -> None:
    assert app_sdk.ProviderManifest is standalone_contracts.ProviderManifest
    assert app_sdk.inspect_provider_module.__module__ == "modular_accounting_provider_sdk.conformance"
    assert app_sdk.scaffold_provider.__module__ == "modular_accounting_provider_sdk.scaffold"


def test_sdk_distribution_metadata_is_zero_dependency_and_application_independent() -> None:
    sdk_root = Path(__file__).resolve().parents[1] / "packages" / "provider-sdk"
    with (sdk_root / "pyproject.toml").open("rb") as handle:
        metadata = tomllib.load(handle)
    assert metadata["project"]["name"] == "modular-accounting-provider-sdk"
    assert metadata["project"]["version"] == "0.5.0"
    assert metadata["project"]["dependencies"] == []
    assert metadata["project"]["license"] == "Apache-2.0"
    forbidden = ("apps", "fastapi", "sqlmodel", "streamlit", "starlette")
    for path in (sdk_root / "src" / "modular_accounting_provider_sdk").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module.split(".", 1)[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
        )
        assert imports.isdisjoint(forbidden), path.name


def test_exact_compatibility_has_stable_codes() -> None:
    compatible = ProviderManifest(
        key="market:author_demo",
        name="Author Demo",
        version="0.1.0",
        api_major=0,
        capabilities=("market",),
    )
    assert check_compatibility(compatible, api_version="0.5.0").to_dict() == {
        "code": "compatible",
        "compatible": True,
        "message": "provider contract is compatible",
    }
    sdk_mismatch = ProviderManifest(
        key=compatible.key,
        name=compatible.name,
        version=compatible.version,
        api_major=0,
        capabilities=compatible.capabilities,
        sdk_version="9.0",
    )
    assert check_compatibility(sdk_mismatch, api_version="0.5.0").code == "sdk.contract.mismatch"
    assert check_compatibility(compatible, api_version="invalid").code == "api.version.invalid"
    assert check_compatibility(compatible, api_version="1.0.0").code == "api.major.mismatch"
    assert PROVIDER_SDK_VERSION == "1.0"


def _snapshot(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


def test_standalone_scaffold_is_deterministic_packaged_and_force_safe(tmp_path: Path) -> None:
    first = scaffold_project(
        tmp_path / "one",
        key="market:external_demo",
        capabilities=("market",),
        description='Safe "quoted" description',
    )
    second = scaffold_project(
        tmp_path / "two",
        key="market:external_demo",
        capabilities=("market",),
        description='Safe "quoted" description',
    )
    assert _snapshot(first.root) == _snapshot(second.root)
    assert first.module == "market_external_demo.provider"
    assert set(_snapshot(first.root)) == {
        "README.md",
        "pyproject.toml",
        "src/market_external_demo/__init__.py",
        "src/market_external_demo/provider.py",
        "src/market_external_demo/py.typed",
        "tests/test_conformance.py",
    }
    provider_source = (first.root / "src/market_external_demo/provider.py").read_text(encoding="utf-8")
    assert "from modular_accounting_provider_sdk import ProviderManifest" in provider_source
    assert "apps." not in provider_source
    assert "\r" not in provider_source
    owner_file = first.root / "author-notes.txt"
    owner_file.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        scaffold_project(tmp_path / "one", key="market:external_demo", capabilities=("market",))
    scaffold_project(tmp_path / "one", key="market:external_demo", capabilities=("market",), force=True)
    assert owner_file.read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize(
    ("distribution", "package"),
    [
        ("Bad Name", None),
        ("safe-name", "../unsafe"),
        ("a--b", None),
    ],
)
def test_standalone_scaffold_rejects_unsafe_names(
    tmp_path: Path,
    distribution: str,
    package: str | None,
) -> None:
    with pytest.raises(ValueError):
        scaffold_project(
            tmp_path,
            key="tax:external_demo",
            capabilities=("tax",),
            distribution=distribution,
            package=package,
        )


def test_provider_and_sdk_artifacts_are_deterministic_installable_inventories(tmp_path: Path) -> None:
    project = scaffold_project(
        tmp_path / "source",
        key="fx:external_demo",
        capabilities=("fx",),
    )
    first = tmp_path / "first"
    second = tmp_path / "second"
    provider_one = (build_project_wheel(project.root, first), build_project_sdist(project.root, first))
    provider_two = (build_project_wheel(project.root, second), build_project_sdist(project.root, second))
    assert [artifact_evidence(path).sha256 for path in provider_one] == [
        artifact_evidence(path).sha256 for path in provider_two
    ]
    assert any(name.endswith("provider.py") for name in artifact_evidence(provider_one[0]).inventory)

    sdk_root = Path(__file__).resolve().parents[1] / "packages" / "provider-sdk"
    sdk_one = (build_sdk_wheel(sdk_root, first), build_sdk_sdist(sdk_root, first))
    sdk_two = (build_sdk_wheel(sdk_root, second), build_sdk_sdist(sdk_root, second))
    assert [artifact_evidence(path).sha256 for path in sdk_one] == [artifact_evidence(path).sha256 for path in sdk_two]
    with zipfile.ZipFile(sdk_one[0]) as archive:
        assert "modular_accounting_provider_sdk/py.typed" in archive.namelist()
        metadata_name = next(name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))
        assert "Requires-Dist:" not in archive.read(metadata_name).decode()
        assert any(name.endswith(".dist-info/licenses/LICENSE") for name in archive.namelist())


def test_artifact_evidence_rejects_unsafe_members(tmp_path: Path) -> None:
    artifact = tmp_path / "unsafe.whl"
    with zipfile.ZipFile(artifact, "w") as archive:
        archive.writestr("../secret.txt", "not a secret")
    with pytest.raises(ValueError, match="unsafe"):
        artifact_evidence(artifact)
    text = tmp_path / "not-an-artifact.txt"
    text.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported"):
        artifact_evidence(text)


def test_standalone_cli_scaffold_validate_and_build(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert (
        main(
            [
                "scaffold",
                "tax:cli_author",
                "--capability",
                "tax",
                "--directory",
                str(tmp_path),
                "--format",
                "json",
            ]
        )
        == 0
    )
    scaffold_payload = json.loads(capsys.readouterr().out)
    assert scaffold_payload["module"] == "tax_cli_author.provider"
    project = tmp_path / scaffold_payload["distribution"]
    monkeypatch.syspath_prepend(str(project / "src"))
    assert (
        main(
            [
                "validate",
                "tax_cli_author.provider",
                "--expected-key",
                "tax:cli_author",
                "--capability",
                "tax",
                "--api-version",
                "0.5.0",
                "--format",
                "json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["passed"] is True
    assert main(["build", str(project), "--format", "json"]) == 0
    build_payload = json.loads(capsys.readouterr().out)
    assert len(build_payload["artifacts"]) == 2


def test_standalone_cli_table_output_covers_author_workflow(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert main(["scaffold", "fx:table_author", "--capability", "fx", "--directory", str(tmp_path)]) == 0
    scaffold_output = capsys.readouterr().out
    assert "Module: fx_table_author.provider" in scaffold_output
    project = tmp_path / "fx-table-author"
    monkeypatch.syspath_prepend(str(project / "src"))
    assert (
        main(
            [
                "validate",
                "fx_table_author.provider",
                "--expected-key",
                "fx:table_author",
                "--capability",
                "fx",
                "--api-version",
                "0.5.0",
            ]
        )
        == 0
    )
    validation = capsys.readouterr().out
    assert "Disposition: PASS" in validation
    assert "FACTORY.RESULT" not in validation
    assert main(["build", str(project)]) == 0
    assert "Artifacts:" in capsys.readouterr().out


def test_standalone_cli_failure_is_bounded_and_stable(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        main(
            [
                "scaffold",
                "bad",
                "--capability",
                "tax",
                "--directory",
                str(tmp_path),
            ]
        )
        == 2
    )
    assert capsys.readouterr().err.startswith("error: key must follow")
    assert main(["validate", "not_real.secret", "--api-version", "0.5.0", "--format", "json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["checks"][0]["message"] == "module import failed (ModuleNotFoundError)"
    assert "secret" not in payload["checks"][0]["message"]

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        standalone_cli,
        "scaffold_project",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("x" * 400)),
    )
    try:
        assert main(["scaffold", "tax:bounded", "--capability", "tax"]) == 2
        assert len(capsys.readouterr().err.strip()) <= 264
    finally:
        monkeypatch.undo()


def test_importable_distribution_does_not_authorize_application_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = scaffold_project(
        tmp_path,
        key="market:installed_untrusted",
        capabilities=("market",),
    )
    monkeypatch.syspath_prepend(str(project.root / "src"))
    assert importlib.util.find_spec("market_installed_untrusted") is not None
    monkeypatch.setattr(plugin_loader.settings, "allowed_providers", {})
    with pytest.raises(ValueError, match="not allowed"):
        plugin_loader.load_provider("market:installed_untrusted")
    assert "market_installed_untrusted.provider" not in sys.modules


def test_build_backend_rejects_malformed_projects_and_exposes_pep517_hooks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "broken"
    root.mkdir()
    (root / "pyproject.toml").write_text("[project]\nname='bad name'\nversion='0.1.0'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="incomplete"):
        build_project_wheel(root, tmp_path / "dist")

    project = scaffold_project(tmp_path, key="bank:backend_demo", capabilities=("bank",))
    monkeypatch.chdir(project.root)
    assert build_wheel(str(tmp_path / "wheel-hooks")).endswith(".whl")
    assert build_sdist(str(tmp_path / "sdist-hooks")).endswith(".tar.gz")
    assert get_requires_for_build_wheel({"ignored": True}) == []
    assert get_requires_for_build_sdist({"ignored": True}) == []

    empty_provider = tmp_path / "empty-provider"
    (empty_provider / "src" / "empty").mkdir(parents=True)
    with pytest.raises(ValueError, match="empty"):
        build_backend._source_files(empty_provider, "empty")
    missing_provider = tmp_path / "missing-provider"
    missing_provider.mkdir()
    with pytest.raises(ValueError, match="missing"):
        build_backend._source_files(missing_provider, "missing")
    empty_sdk = tmp_path / "empty-sdk"
    (empty_sdk / "src" / "modular_accounting_provider_sdk").mkdir(parents=True)
    with pytest.raises(ValueError, match="empty"):
        build_backend._sdk_files(empty_sdk)
