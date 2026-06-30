"""Lightweight repository-scoped secret scanner for CI quality gates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
}

TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".txt",
    ".toml",
    ".yml",
    ".yaml",
    ".json",
    ".env",
    ".ini",
    ".cfg",
    ".sh",
    ".ps1",
    ".cjs",
}

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "aws_access_key",
        re.compile(r"\b(AKIA|ASIA)[A-Z0-9]{16}\b"),
    ),
    (
        "github_token",
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    ),
    (
        "openai_key",
        re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    ),
    (
        "private_key_header",
        re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
    (
        "generic_secret_assignment",
        re.compile(r"(?i)(secret|token|api[_-]?key|password)\s*[:=]\s*['\"][^'\"]{10,}['\"]"),
    ),
)


@dataclass(slots=True)
class Finding:
    path: Path
    line: int
    kind: str
    excerpt: str


def _is_candidate(path: Path) -> bool:
    if path.suffix.lower() in TEXT_SUFFIXES:
        return True
    return path.name in {"Dockerfile", "Makefile", ".env.example"}


def _iter_files() -> list[Path]:
    files: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        if any(part in IGNORE_DIRS or part.startswith(".venv") for part in path.parts):
            continue
        if not path.is_file():
            continue
        if _is_candidate(path):
            files.append(path)
    return files


def _scan_file(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return findings

    for index, line in enumerate(lines, start=1):
        for kind, pattern in PATTERNS:
            if pattern.search(line):
                findings.append(Finding(path=path.relative_to(REPO_ROOT), line=index, kind=kind, excerpt=line.strip()))
    return findings


def main() -> int:
    findings: list[Finding] = []
    for file_path in _iter_files():
        findings.extend(_scan_file(file_path))

    if findings:
        print("Potential secrets detected:")
        for finding in findings:
            print(f"- {finding.path}:{finding.line} [{finding.kind}] {finding.excerpt}")
        return 1

    print("Secret scan passed: no high-confidence secret patterns found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
