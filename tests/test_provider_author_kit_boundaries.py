"""Path, archive, metadata, and sanitized-failure regressions for the author kit."""

from __future__ import annotations

import io
import json
import os
import stat
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from modular_accounting_provider_sdk import (
    AuthorKitBoundaryError,
    artifact_evidence,
    cli,
    evidence,
    extract_sdist_safely,
    inspect_provider_module,
    path_safety,
    scaffold_project,
    validate_provider_module,
)
from modular_accounting_provider_sdk.build_backend import build_project_sdist, build_project_wheel, build_sdk_wheel


@pytest.mark.parametrize(
    "module",
    (
        "../escape.provider",
        "safe/escape.provider",
        "safe\\escape.provider",
        "C:drive.provider",
        "https:remote.provider",
        ".provider",
        "safe..provider",
        "safe.module",
        "safe.\x00.provider",
        "a" * 260 + ".provider",
    ),
)
def test_provider_module_grammar_rejects_path_like_values_before_import(module: str) -> None:
    with pytest.raises(AuthorKitBoundaryError, match="metadata is invalid"):
        validate_provider_module(module)
    report = inspect_provider_module(module)
    assert report.module == "invalid.provider"
    assert report.failure_codes == ("module.name",)


def test_provider_module_grammar_rejects_non_text() -> None:
    with pytest.raises(AuthorKitBoundaryError, match="metadata is invalid"):
        validate_provider_module(7)  # type: ignore[arg-type]


def _zip(path: Path, names: tuple[str, ...]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name in names:
            archive.writestr(name, b"bounded")


@pytest.mark.parametrize(
    "name",
    (
        "/absolute/path",
        "C:/drive/path",
        "C:\\drive\\path",
        "\\\\server\\share\\path",
        "safe/../escape",
        "safe//empty",
        "safe/./dot",
    ),
)
def test_artifact_inventory_rejects_unsafe_absolute_and_traversal_members(tmp_path: Path, name: str) -> None:
    artifact = tmp_path / "unsafe.whl"
    _zip(artifact, (name,))
    with pytest.raises(AuthorKitBoundaryError, match="unsafe member"):
        artifact_evidence(artifact)


def test_artifact_inventory_rejects_control_characters_before_archive_normalization() -> None:
    with pytest.raises(AuthorKitBoundaryError, match="unsafe member"):
        evidence._safe_members(("safe/\x00control",))


def test_artifact_inventory_rejects_duplicate_normalized_and_zip_link_members(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.whl"
    _zip(duplicate, ("package/file.py", "PACKAGE/FILE.py"))
    with pytest.raises(AuthorKitBoundaryError, match="duplicate"):
        artifact_evidence(duplicate)

    linked = tmp_path / "linked.whl"
    info = zipfile.ZipInfo("package/provider.py")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(linked, "w") as archive:
        archive.writestr(info, "outside")
    with pytest.raises(AuthorKitBoundaryError, match="non-regular"):
        artifact_evidence(linked)


def test_artifact_inventory_bounds_member_count_name_and_expanded_size(tmp_path: Path, monkeypatch) -> None:
    with pytest.raises(AuthorKitBoundaryError, match="member limit"):
        evidence._safe_members(tuple(f"safe/{index}" for index in range(4097)))
    with pytest.raises(AuthorKitBoundaryError, match="unsafe member"):
        evidence._safe_members(("safe/" + "a" * 260,))

    artifact = tmp_path / "expanded.whl"
    _zip(artifact, ("safe/file",))
    with zipfile.ZipFile(artifact) as archive:
        monkeypatch.setattr(evidence, "_MAX_UNCOMPRESSED_BYTES", 1)
        with pytest.raises(AuthorKitBoundaryError, match="expanded size"):
            evidence._zip_inventory(archive)


@pytest.mark.parametrize("link_type", (tarfile.SYMTYPE, tarfile.LNKTYPE))
def test_artifact_inventory_rejects_tar_links(tmp_path: Path, link_type: bytes) -> None:
    artifact = tmp_path / "linked.tar.gz"
    with tarfile.open(artifact, "w:gz") as archive:
        info = tarfile.TarInfo("package/provider.py")
        info.type = link_type
        info.linkname = "outside"
        archive.addfile(info)
    with pytest.raises(AuthorKitBoundaryError, match="non-regular"):
        artifact_evidence(artifact)


def test_safe_sdist_extraction_rejects_multiple_source_roots(tmp_path: Path) -> None:
    artifact = tmp_path / "malformed.tar.gz"
    with tarfile.open(artifact, "w:gz") as archive:
        for name in ("first/pyproject.toml", "second/provider.py"):
            content = b"bounded"
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    with pytest.raises(AuthorKitBoundaryError, match="source root is malformed"):
        extract_sdist_safely(artifact, tmp_path / "extract")


def test_safe_sdist_extraction_and_wheel_record_validation(tmp_path: Path) -> None:
    project = scaffold_project(tmp_path / "source", key="market:record", capabilities=("market",))
    artifacts = tmp_path / "artifacts"
    wheel = build_project_wheel(project.root, artifacts)
    sdist = build_project_sdist(project.root, artifacts)
    assert evidence.validate_wheel_record(wheel)
    extracted = extract_sdist_safely(sdist, tmp_path / "extracted")
    assert (extracted / "src" / project.package / "provider.py").is_file()
    with pytest.raises(AuthorKitBoundaryError, match="target is unsafe"):
        extract_sdist_safely(sdist, tmp_path / "extracted")


def test_wheel_record_rejects_missing_inventory_and_invalid_hash(tmp_path: Path) -> None:
    sdk_root = Path(__file__).resolve().parents[1] / "packages" / "provider-sdk"
    wheel = build_sdk_wheel(sdk_root, tmp_path / "dist")
    rewritten = tmp_path / "invalid.whl"
    with zipfile.ZipFile(wheel) as source, zipfile.ZipFile(rewritten, "w") as target:
        for info in source.infolist():
            content = source.read(info.filename)
            if info.filename.endswith(".dist-info/RECORD"):
                content = content.replace(b"sha256=", b"sha256=broken", 1)
            target.writestr(info, content)
    with pytest.raises(AuthorKitBoundaryError, match="hash or size"):
        evidence.validate_wheel_record(rewritten)

    missing = tmp_path / "missing-record.whl"
    _zip(missing, ("package/provider.py",))
    with pytest.raises(AuthorKitBoundaryError, match="RECORD"):
        evidence.validate_wheel_record(missing)


def test_artifact_evidence_rejects_missing_oversized_and_malformed_files(tmp_path: Path, monkeypatch) -> None:
    with pytest.raises(AuthorKitBoundaryError, match="not found"):
        evidence.sha256_file(tmp_path / "missing.whl")
    artifact = tmp_path / "oversized.whl"
    artifact.write_bytes(b"bounded")
    monkeypatch.setattr(evidence, "_MAX_ARTIFACT_BYTES", 1)
    with pytest.raises(AuthorKitBoundaryError, match="size limit"):
        evidence.sha256_file(artifact)
    malformed = tmp_path / "malformed.whl"
    malformed.write_bytes(b"not-a-zip")
    with pytest.raises(AuthorKitBoundaryError, match="inspected"):
        artifact_evidence(malformed)


def test_source_file_link_escape_is_rejected_without_reading_target(tmp_path: Path, monkeypatch) -> None:
    project = scaffold_project(tmp_path, key="market:link_escape", capabilities=("market",))
    provider = project.root / "src" / project.package / "provider.py"
    sentinel = tmp_path / "outside-sentinel.py"
    sentinel.write_text("ABSOLUTE_SENTINEL", encoding="utf-8")
    provider.unlink()
    try:
        provider.symlink_to(sentinel)
    except OSError:
        provider.write_text("bounded", encoding="utf-8")
        original = path_safety._is_link_or_reparse
        monkeypatch.setattr(path_safety, "_is_link_or_reparse", lambda path: path == provider or original(path))
    with pytest.raises(AuthorKitBoundaryError, match="unsafe"):
        build_project_wheel(project.root, tmp_path / "dist")


def test_force_regeneration_rejects_link_target_and_preserves_sentinel(tmp_path: Path, monkeypatch) -> None:
    project = scaffold_project(tmp_path, key="tax:force_escape", capabilities=("tax",))
    target = project.root / "README.md"
    sentinel = tmp_path / "outside-sentinel.txt"
    sentinel.write_text("KEEP_SENTINEL", encoding="utf-8")
    target.unlink()
    try:
        target.symlink_to(sentinel)
    except OSError:
        target.write_text("bounded", encoding="utf-8")
        original = path_safety._is_link_or_reparse
        monkeypatch.setattr(path_safety, "_is_link_or_reparse", lambda path: path == target or original(path))
    with pytest.raises(AuthorKitBoundaryError, match="generated target is unsafe"):
        scaffold_project(tmp_path, key="tax:force_escape", capabilities=("tax",), force=True)
    assert sentinel.read_text(encoding="utf-8") == "KEEP_SENTINEL"


def test_simulated_source_directory_reparse_point_is_rejected(tmp_path: Path, monkeypatch) -> None:
    project = scaffold_project(tmp_path, key="fx:reparse", capabilities=("fx",))
    source = project.root / "src" / project.package
    original = path_safety._is_link_or_reparse
    monkeypatch.setattr(path_safety, "_is_link_or_reparse", lambda path: path == source or original(path))
    with pytest.raises(AuthorKitBoundaryError, match="unsafe"):
        build_project_wheel(project.root, tmp_path / "dist")


def test_resolved_path_helpers_fail_closed_for_missing_outside_and_unsafe_targets(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(AuthorKitBoundaryError, match="not found"):
        path_safety.resolved_directory(missing)
    created = path_safety.resolved_directory(missing, create=True)
    assert created == missing.resolve()
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("bounded", encoding="utf-8")
    with pytest.raises(AuthorKitBoundaryError, match="unsafe"):
        path_safety.ordinary_file(root, outside)
    with pytest.raises(AuthorKitBoundaryError, match="not found"):
        path_safety.ordinary_file(root, root / "missing.txt")
    with pytest.raises(AuthorKitBoundaryError, match="unsafe"):
        path_safety.validate_generated_targets(root, (outside,))


def test_safe_source_collection_rejects_simulated_child_directory_link(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "root"
    source = root / "src"
    child = source / "child"
    child.mkdir(parents=True)
    (child / "provider.py").write_text("bounded", encoding="utf-8")
    original = path_safety._is_link_or_reparse
    monkeypatch.setattr(path_safety, "_is_link_or_reparse", lambda path: path == child or original(path))
    with pytest.raises(AuthorKitBoundaryError, match="unsafe"):
        path_safety.safe_source_files(root, source)


def test_missing_project_cli_json_is_stable_and_path_free(tmp_path: Path, capsys) -> None:
    sentinel = tmp_path / "ABSOLUTE_PATH_SENTINEL" / "missing"
    assert cli.main(["build", str(sentinel), "--format", "json"]) == 2
    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload == {"code": "project.not_found", "message": "project directory was not found"}
    combined = output.out + output.err
    assert str(sentinel) not in combined
    assert "ABSOLUTE_PATH_SENTINEL" not in combined


def test_generated_provider_declares_exact_sdk_build_requirement(tmp_path: Path) -> None:
    project = scaffold_project(tmp_path, key="bank:declared_backend", capabilities=("bank",))
    text = (project.root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'requires = ["modular-accounting-provider-sdk==0.5.0"]' in text
    assert 'build-backend = "modular_accounting_provider_sdk.build_backend"' in text
    assert os.linesep not in text or "\r\n" not in text


def test_clean_source_startup_uses_both_documented_roots(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["MODACCT_DATABASE_URL"] = "sqlite://"
    env["PYTHONPATH"] = os.pathsep.join((str(root / "src"), str(root / "packages" / "provider-sdk" / "src")))
    for statement in ("import apps.provider_sdk", "import apps.api.main"):
        completed = subprocess.run(
            [sys.executable, "-c", statement],
            cwd=root,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr

    launcher = (root / "apps" / "web" / "app.py").read_text(encoding="utf-8")
    assert '"packages" / "provider-sdk" / "src"' in launcher
    assert "for source_root in (SDK_ROOT, SRC_ROOT)" in launcher


def test_ci_uploads_exact_identity_author_acceptance_evidence() -> None:
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "PROVIDER_ACCEPTANCE_SOURCE_HEAD" in workflow
    assert "PROVIDER_ACCEPTANCE_TESTED_COMMIT" in workflow
    assert "provider-author-acceptance.json" in workflow
    assert "fetch-depth: 0" in workflow


def test_path_safety_is_an_explicit_critical_coverage_boundary() -> None:
    policy = (Path(__file__).resolve().parents[1] / "config" / "critical-coverage.toml").read_text(encoding="utf-8")
    marker = 'path = "packages/provider-sdk/src/modular_accounting_provider_sdk/path_safety.py"'
    assert marker in policy
    section = policy.split(marker, 1)[1].split("[[module]]", 1)[0]
    assert "line_floor = 85.0" in section
    assert "branch_floor = 80.0" in section
