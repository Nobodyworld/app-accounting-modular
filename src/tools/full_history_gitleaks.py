"""Run a verified, redacted Gitleaks scan over all reachable public refs."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VERSION = "8.30.1"
RELEASE_BASE = f"https://github.com/gitleaks/gitleaks/releases/download/v{VERSION}"
CHECKSUMS_NAME = f"gitleaks_{VERSION}_checksums.txt"


def _run(*args: str, cwd: Path = REPO_ROOT) -> str:
    completed = subprocess.run(
        args,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "command failed"
        raise RuntimeError(f"{' '.join(args)}: {detail}")
    return completed.stdout.strip()


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "app-accounting-modular-ci"})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as target:
        shutil.copyfileobj(response, target)


def _archive_name() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system != "linux" or machine not in {"x86_64", "amd64"}:
        raise RuntimeError(f"unsupported hosted scan platform: {system}/{machine}")
    return f"gitleaks_{VERSION}_linux_x64.tar.gz"


def _expected_checksum(checksums_path: Path, archive_name: str) -> str:
    matches: list[str] = []
    for raw_line in checksums_path.read_text(encoding="utf-8").splitlines():
        parts = raw_line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == archive_name:
            matches.append(parts[0].lower())
    if len(matches) != 1 or len(matches[0]) != 64:
        raise RuntimeError(f"official checksum manifest lacks one valid entry for {archive_name}")
    return matches[0]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fetch_all_public_refs() -> None:
    shallow = _run("git", "rev-parse", "--is-shallow-repository")
    if shallow == "true":
        _run("git", "fetch", "--unshallow", "--tags", "origin")
    _run(
        "git",
        "fetch",
        "--force",
        "--prune",
        "--tags",
        "origin",
        "+refs/heads/*:refs/remotes/origin/*",
    )


def main() -> int:
    _fetch_all_public_refs()
    reachable_commits = int(_run("git", "rev-list", "--all", "--count"))
    root_commits = sorted(line for line in _run("git", "rev-list", "--all", "--max-parents=0").splitlines() if line)
    scanned_head = _run("git", "rev-parse", "HEAD")

    archive_name = _archive_name()
    with tempfile.TemporaryDirectory(prefix="modacct-gitleaks-") as raw_temp:
        temp = Path(raw_temp)
        checksums_path = temp / CHECKSUMS_NAME
        archive_path = temp / archive_name
        _download(f"{RELEASE_BASE}/{CHECKSUMS_NAME}", checksums_path)
        _download(f"{RELEASE_BASE}/{archive_name}", archive_path)

        expected = _expected_checksum(checksums_path, archive_name)
        actual = _sha256(archive_path)
        if actual != expected:
            raise RuntimeError(f"Gitleaks archive checksum mismatch: expected {expected}, got {actual}")

        install_dir = temp / "install"
        install_dir.mkdir()
        with tarfile.open(archive_path, "r:gz") as archive:
            members = archive.getmembers()
            binary_members = [member for member in members if Path(member.name).name == "gitleaks" and member.isfile()]
            if len(binary_members) != 1:
                raise RuntimeError("Gitleaks archive does not contain exactly one binary")
            binary_member = binary_members[0]
            binary_member.name = "gitleaks"
            archive.extract(binary_member, install_dir, filter="data")

        binary = install_dir / "gitleaks"
        binary.chmod(0o755)
        version_output = _run(str(binary), "version")
        if VERSION not in version_output:
            raise RuntimeError(f"unexpected Gitleaks version output: {version_output}")

        report_path = temp / "gitleaks-full-history.json"
        completed = subprocess.run(
            (
                str(binary),
                "git",
                ".",
                "--log-opts=--all",
                "--redact",
                "--report-format=json",
                f"--report-path={report_path}",
                "--exit-code=1",
            ),
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "NO_COLOR": "1"},
        )
        if not report_path.exists():
            raise RuntimeError("Gitleaks did not create the requested JSON report")
        report_payload = json.loads(report_path.read_text(encoding="utf-8") or "[]")
        if not isinstance(report_payload, list):
            raise RuntimeError("Gitleaks report is not a JSON array")
        if completed.returncode != 0 or report_payload:
            raise RuntimeError(
                f"Gitleaks full-history scan failed: exit={completed.returncode}, findings={len(report_payload)}"
            )

        evidence = {
            "gitleaks_version": version_output,
            "gitleaks_release_commit": "83d9cd6",
            "archive_name": archive_name,
            "archive_sha256": actual,
            "reachable_commits": reachable_commits,
            "root_commits": root_commits,
            "scanned_head": scanned_head,
            "findings": 0,
            "report_sha256": _sha256(report_path),
        }
        print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
