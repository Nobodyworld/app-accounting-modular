"""Generate the hashed runtime lock inside the pinned Python container."""

from __future__ import annotations

import platform
import subprocess
import sys
import tempfile
from pathlib import Path

from verify_container_lock import (
    BASE_IMAGE,
    GENERATOR_NAME,
    GENERATOR_VERSION,
    PLATFORM_POLICY,
    PYTHON_POLICY,
    REPO_ROOT,
    RUNTIME_INPUT,
    RUNTIME_LOCK,
    canonical_sha256,
    verify_container_lock,
)

UV_EXECUTABLE = Path(sys.executable).with_name(GENERATOR_NAME)


def _assert_generation_environment() -> None:
    errors: list[str] = []
    if platform.system() != "Linux":
        errors.append(f"generation must run in Linux; found {platform.system()}")
    if platform.machine().lower() not in {"amd64", "x86_64"}:
        errors.append(f"generation must run on linux/amd64; found {platform.machine()}")
    if sys.version_info[:2] != (3, 14):
        errors.append(f"generation requires Python 3.14; found {platform.python_version()}")

    completed = subprocess.run(
        [str(UV_EXECUTABLE), "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    expected_prefix = f"{GENERATOR_NAME} {GENERATOR_VERSION} "
    if completed.returncode != 0:
        errors.append(f"unable to run {GENERATOR_NAME}: {completed.stderr.strip()}")
    elif not completed.stdout.startswith(expected_prefix):
        errors.append(f"generation requires {GENERATOR_NAME}=={GENERATOR_VERSION}; found {completed.stdout.strip()}")
    if errors:
        raise RuntimeError("\n".join(errors))


def _write_lf(path: Path, content: str) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    temporary.replace(path)


def generate(input_path: Path, output_path: Path) -> None:
    _assert_generation_environment()
    input_sha256 = canonical_sha256(input_path.read_bytes())

    with tempfile.TemporaryDirectory(prefix="modacct-container-lock-") as temp_directory:
        raw_lock = Path(temp_directory) / "requirements-container.raw"
        command = [
            str(UV_EXECUTABLE),
            "--quiet",
            "pip",
            "compile",
            str(input_path),
            "--output-file",
            str(raw_lock),
            "--format",
            "requirements.txt",
            "--generate-hashes",
            "--no-annotate",
            "--no-header",
            "--no-strip-extras",
            "--no-strip-markers",
            "--python",
            sys.executable,
            "--python-version",
            PYTHON_POLICY,
            "--python-platform",
            "x86_64-manylinux_2_28",
            "--only-binary",
            ":all:",
            "--no-cache",
            "--no-sources",
            "--no-python-downloads",
            "--index-strategy",
            "first-index",
        ]
        subprocess.run(command, check=True, cwd=REPO_ROOT)
        body = raw_lock.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n").strip()

    header = "\n".join(
        (
            "# Generated container runtime lock. Do not edit by hand.",
            f"# input-file: {RUNTIME_INPUT}",
            f"# input-sha256: {input_sha256}",
            f"# generator: {GENERATOR_NAME}",
            f"# generator-version: {GENERATOR_VERSION}",
            f"# python-version: {PYTHON_POLICY}",
            f"# platform: {PLATFORM_POLICY}",
            f"# base-image: {BASE_IMAGE}",
            "# generated-command: scripts/dependencies/Generate-ContainerLock.ps1",
        )
    )
    _write_lf(output_path, f"{header}\n\n{body}\n")

    summary = verify_container_lock(output_path, input_path)
    print(
        f"generated {output_path.name}: requirements={summary.requirement_count} "
        f"direct={summary.direct_requirement_count} transitive={summary.transitive_requirement_count} "
        f"sha256={summary.sha256}"
    )


def main() -> int:
    generate(REPO_ROOT / RUNTIME_INPUT, REPO_ROOT / RUNTIME_LOCK)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
