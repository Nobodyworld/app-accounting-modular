"""Run the repository quality gate (lint, type, tests, security)."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

COMMANDS: Sequence[Sequence[str]] = (
    (sys.executable, "-m", "ruff", "check", "."),
    (sys.executable, "-m", "ruff", "format", "--check", "."),
    (
        sys.executable,
        "-m",
        "mypy",
        "src/apps/modular_accounting/application",
        "src/apps/api",
        "src/apps/extensions",
        "src/cli",
    ),
    (
        sys.executable,
        "-m",
        "pytest",
        "-o",
        "cache_dir=.pytest_cache_runtime",
        "--cov=src/apps",
        "--cov=src/plugins",
        "--cov=src/cli",
        "--cov-report=term-missing",
        "--cov-fail-under=85",
    ),
    (
        sys.executable,
        "-m",
        "pytest",
        "-o",
        "cache_dir=.pytest_cache_runtime",
        "-q",
        "tests/test_ledger_service.py",
        "tests/test_data_snapshot_service.py",
        "tests/test_modular_accounting_snapshot.py",
        "tests/test_modular_accounting_controls.py",
    ),
    (sys.executable, "-m", "pip", "check"),
    (
        sys.executable,
        "-m",
        "pip_audit",
        "--timeout",
        "60",
        "-r",
        "requirements.txt",
        "-r",
        "requirements-dev.txt",
    ),
    (sys.executable, "-m", "src.tools.secret_scan"),
)


@dataclass(slots=True)
class CommandResult:
    command: Sequence[str]
    returncode: int
    error: str | None = None
    skipped: bool = False

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0


def _run_command(command: Sequence[str]) -> CommandResult:
    env = os.environ.copy()
    src_path = str(REPO_ROOT / "src")
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src_path if not existing_pythonpath else f"{src_path}{os.pathsep}{existing_pythonpath}"
    try:
        completed = subprocess.run(command, check=False, cwd=str(REPO_ROOT), env=env)
    except FileNotFoundError as exc:
        return CommandResult(command=command, returncode=127, error=str(exc), skipped=True)
    return CommandResult(command=command, returncode=completed.returncode)


def main() -> int:
    results = [_run_command(command) for command in COMMANDS]
    skipped = [result for result in results if result.skipped]

    for result in results:
        joined = " ".join(result.command)
        status = "skipped" if result.skipped else ("ok" if result.succeeded else "failed")
        print(f"[{status}] command={joined}")
        print(f"    exit_code={result.returncode}")
        if result.error:
            print(f"    error: {result.error}")

    if skipped:
        print(f"\nSkipped tools: {len(skipped)}")
        for result in skipped:
            print(f"- {' '.join(result.command)}")
    else:
        print("\nSkipped tools: none")

    failures = [result for result in results if not result.succeeded]
    if failures:
        print("\nQuality gate failed. Resolve the commands above before retrying.")
        return 1
    print("\nQuality gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
