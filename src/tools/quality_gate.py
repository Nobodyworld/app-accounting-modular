"""Run the repository quality gate (lint, type, test, security)."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass

COMMANDS: Sequence[Sequence[str]] = (
    ("ruff", "check", "."),
    (
        "mypy",
        "apps/modular_accounting/application",
        "apps/api",
        "apps/extensions",
        "cli",
        "tests",
    ),
    (
        "pytest",
        "--cov=apps",
        "--cov=plugins",
        "--cov=cli",
        "--cov-report=term-missing",
        "--cov-fail-under=85",
    ),
    (sys.executable, "-m", "safety", "check", "--full-report"),
)


@dataclass(slots=True)
class CommandResult:
    command: Sequence[str]
    returncode: int
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0


def _run_command(command: Sequence[str]) -> CommandResult:
    try:
        completed = subprocess.run(command, check=False)
    except FileNotFoundError as exc:
        return CommandResult(command=command, returncode=127, error=str(exc))
    return CommandResult(command=command, returncode=completed.returncode)


def main() -> int:
    results = [_run_command(command) for command in COMMANDS]
    for result in results:
        joined = " ".join(result.command)
        status = "ok" if result.succeeded else "failed"
        print(f"[{status}] {joined}")
        if result.error:
            print(f"    error: {result.error}")
    failures = [result for result in results if not result.succeeded]
    if failures:
        print("\nQuality gate failed. Resolve the commands above before retrying.")
        return 1
    print("\nQuality gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
