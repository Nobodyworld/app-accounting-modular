"""Policy tests for reproducible and attestable container dependencies."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from scripts.dependencies.verify_container_lock import (
    BASE_IMAGE,
    LockValidationError,
    canonical_sha256,
    validate_container_lock_text,
    verify_container_lock,
    verify_tool_lock,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILES = (REPO_ROOT / "config" / "Dockerfile.api", REPO_ROOT / "config" / "Dockerfile.web")
RUNTIME_INPUT = REPO_ROOT / "requirements.txt"
RUNTIME_LOCK = REPO_ROOT / "requirements-container.lock"
TOOL_LOCK = REPO_ROOT / "requirements-lock-tools.lock"
POWERSHELL_GENERATOR = REPO_ROOT / "scripts" / "dependencies" / "Generate-ContainerLock.ps1"
LINUX_GENERATOR = REPO_ROOT / "scripts" / "dependencies" / "generate-container-lock.sh"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"

BASE_PATTERN = re.compile(r"^FROM (python:3\.14-slim@sha256:[0-9a-f]{64})$", re.MULTILINE)


def _dockerfile_texts() -> list[str]:
    return [path.read_text(encoding="utf-8") for path in DOCKERFILES]


def _replace_first_logical_requirement(lock_text: str, replacement: str) -> str:
    lines = lock_text.splitlines()
    start = next(index for index, line in enumerate(lines) if line and not line.startswith("#"))
    end = start
    while lines[end].rstrip().endswith("\\"):
        end += 1
    return "\n".join([*lines[:start], replacement, *lines[end + 1 :]]) + "\n"


def test_both_dockerfiles_use_the_same_valid_digest_pinned_base() -> None:
    references = []
    for dockerfile in _dockerfile_texts():
        match = BASE_PATTERN.search(dockerfile)
        assert match is not None
        references.append(match.group(1))

    assert references == [BASE_IMAGE, BASE_IMAGE]


def test_no_mutable_base_override_or_pip_upgrade_remains() -> None:
    for dockerfile in _dockerfile_texts():
        lowered = dockerfile.lower()
        assert "arg python_image" not in lowered
        assert "from ${python_image}" not in lowered
        assert "pip install --upgrade pip" not in lowered
        assert "pip install -u pip" not in lowered


def test_dockerfiles_install_only_the_hashed_runtime_lock() -> None:
    required_tokens = (
        "COPY requirements-container.lock ./",
        "--disable-pip-version-check",
        "--no-cache-dir",
        "--require-hashes",
        "--only-binary=:all:",
        "--no-deps",
        "-r requirements-container.lock",
        "python -m pip check",
    )
    for dockerfile in _dockerfile_texts():
        for token in required_tokens:
            assert token in dockerfile
        assert "COPY requirements.txt" not in dockerfile
        assert "-r requirements.txt" not in dockerfile


def test_runtime_lock_passes_offline_policy_validation() -> None:
    summary = verify_container_lock(RUNTIME_LOCK, RUNTIME_INPUT)

    assert summary.requirement_count == 77
    assert summary.direct_requirement_count == 19
    assert summary.transitive_requirement_count == 58
    assert len(summary.sha256) == 64


def test_runtime_lock_fingerprint_matches_canonical_input() -> None:
    input_fingerprint = canonical_sha256(RUNTIME_INPUT.read_bytes())
    lock_text = RUNTIME_LOCK.read_text(encoding="utf-8")

    assert input_fingerprint == "4f5586d77750784f6e71a9bd041ff6122558c7c216599bc1a0e3f78e0ac502e3"
    assert f"# input-sha256: {input_fingerprint}" in lock_text


def test_removed_hash_is_rejected() -> None:
    lock_text = RUNTIME_LOCK.read_text(encoding="utf-8")
    first_requirement = next(
        line.rstrip().removesuffix("\\").rstrip()
        for line in lock_text.splitlines()
        if line and not line.startswith("#")
    )
    mutated = _replace_first_logical_requirement(lock_text, first_requirement)

    with pytest.raises(LockValidationError, match="has no SHA-256 hash"):
        validate_container_lock_text(mutated, RUNTIME_INPUT.read_bytes())


def test_altered_input_manifest_is_rejected() -> None:
    altered_input = RUNTIME_INPUT.read_bytes() + b"\nexample-package>=1,<2\n"

    with pytest.raises(LockValidationError, match="input-sha256"):
        validate_container_lock_text(RUNTIME_LOCK.read_text(encoding="utf-8"), altered_input)


@pytest.mark.parametrize(
    "invalid_requirement, expected_message",
    (
        ("-e git+https://example.invalid/project.git#egg=project", "VCS"),
        ("project @ https://example.invalid/project.whl", "direct URL"),
        ("project==1.0", "has no SHA-256 hash"),
        ("project>=1.0 --hash=sha256:" + "a" * 64, "not an exact"),
        ("project==1.* --hash=sha256:" + "a" * 64, "not a concrete"),
        ("project==1.0,==2.0 --hash=sha256:" + "a" * 64, "not a concrete"),
    ),
)
def test_editable_vcs_url_unhashed_and_inexact_requirements_are_rejected(
    invalid_requirement: str,
    expected_message: str,
) -> None:
    lock_text = RUNTIME_LOCK.read_text(encoding="utf-8")
    mutated = _replace_first_logical_requirement(lock_text, invalid_requirement)

    with pytest.raises(LockValidationError, match=expected_message):
        validate_container_lock_text(mutated, RUNTIME_INPUT.read_bytes())


def test_required_extras_are_preserved() -> None:
    lock_text = RUNTIME_LOCK.read_text(encoding="utf-8").lower()

    assert re.search(r"^uvicorn\[standard\]==", lock_text, re.MULTILINE)
    assert re.search(r"^pyjwt\[crypto\]==", lock_text, re.MULTILINE)


def test_lock_generation_toolchain_is_exact_hashed_and_isolated() -> None:
    summary = verify_tool_lock(TOOL_LOCK)
    tool_lock = TOOL_LOCK.read_text(encoding="utf-8")

    assert summary.package_versions == {"uv": "0.12.0"}
    assert "uv==0.12.0" in tool_lock
    assert "--hash=sha256:" in tool_lock
    assert "--require-hashes" in POWERSHELL_GENERATOR.read_text(encoding="utf-8")
    assert "--require-hashes" in LINUX_GENERATOR.read_text(encoding="utf-8")


def test_generators_use_the_same_pinned_image_and_binary_only_resolution() -> None:
    for generator in (POWERSHELL_GENERATOR, LINUX_GENERATOR):
        text = generator.read_text(encoding="utf-8")
        assert BASE_IMAGE in text
        assert "--platform linux/amd64" in text
        assert "--only-binary=:all:" in text
        assert "requirements-lock-tools.lock" in text


def test_workflow_action_references_are_full_commit_shas() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    action_references = re.findall(r"^\s*uses:\s*([^\s]+)$", workflow, re.MULTILINE)

    assert action_references
    for reference in action_references:
        assert re.fullmatch(r"[^@\s]+@[0-9a-f]{40}", reference), reference


def test_consolidated_dependency_versions_and_manifest_floors_are_explicit() -> None:
    manifest = RUNTIME_INPUT.read_text(encoding="utf-8").lower()
    lock_text = RUNTIME_LOCK.read_text(encoding="utf-8").lower()

    assert "streamlit>=1.61.1,<2.0" in manifest
    assert "pyjwt[crypto]>=2.13.0,<3.0" in manifest
    assert re.search(r"^streamlit==1\.61\.1 \\", lock_text, re.MULTILINE)
    assert re.search(r"^pyjwt\[crypto\]==2\.13\.0 \\", lock_text, re.MULTILINE)


def test_dependabot_avoids_unnecessary_floor_only_updates() -> None:
    dependabot = (REPO_ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")

    pip_section = dependabot.split("# GitHub Actions updates", maxsplit=1)[0]
    assert "package-ecosystem: pip" in pip_section
    assert "versioning-strategy: increase-if-necessary" in pip_section


def test_attestation_action_is_exactly_pinned_to_v4_2_2() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    reference = "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6"
    release_comment = "actions/attest v4.2.2 (released 2026-08-04; resolved 2026-08-12)"

    assert workflow.count(reference) == 4
    assert workflow.count(release_comment) == 4
    assert "actions/attest@508db95dd578ae2727ebd6217d5ba78e4fbda05d" not in workflow
