"""Evaluate changed executable production lines against Coverage.py JSON evidence."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import subprocess
import sys
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HUNK_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? "
    r"\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@"
)


@dataclass(frozen=True, slots=True)
class DiffCoveragePolicy:
    include_roots: tuple[str, ...]
    exclude: tuple[str, ...]
    minimum_changed_line_percent: float
    allow_no_changed_executable_lines: bool = True


@dataclass(frozen=True, slots=True)
class GitContext:
    base_sha: str
    head_sha: str
    merge_base_sha: str


@dataclass(frozen=True, slots=True)
class FileCoverage:
    path: str
    changed_lines: tuple[int, ...]
    executable_lines: tuple[int, ...]
    covered_lines: tuple[int, ...]
    missed_lines: tuple[int, ...]

    @property
    def percent(self) -> float | None:
        if not self.executable_lines:
            return None
        return len(self.covered_lines) / len(self.executable_lines) * 100


@dataclass(frozen=True, slots=True)
class DiffCoverageResult:
    context: GitContext
    policy: DiffCoveragePolicy
    policy_sha256: str
    files: tuple[FileCoverage, ...]

    @property
    def executable_line_count(self) -> int:
        return sum(len(item.executable_lines) for item in self.files)

    @property
    def covered_line_count(self) -> int:
        return sum(len(item.covered_lines) for item in self.files)

    @property
    def missed_line_count(self) -> int:
        return sum(len(item.missed_lines) for item in self.files)

    @property
    def percent(self) -> float | None:
        if self.executable_line_count == 0:
            return None
        return self.covered_line_count / self.executable_line_count * 100

    @property
    def passed(self) -> bool:
        if self.percent is None:
            return self.policy.allow_no_changed_executable_lines
        return self.percent >= self.policy.minimum_changed_line_percent


def _normalize_path(value: str) -> str:
    normalized = value.replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lstrip("/")


def _percentage(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    result = float(value)
    if not 0 <= result <= 100:
        raise ValueError(f"{label} must be between 0 and 100")
    return result


def _string_tuple(value: object, label: str, *, allow_empty: bool) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array of paths")
    normalized: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{label}[{index}] must be a nonempty path")
        path = _normalize_path(item)
        if path in normalized:
            raise ValueError(f"{label} contains a duplicate path: {path}")
        normalized.append(path)
    if not normalized and not allow_empty:
        raise ValueError(f"{label} must not be empty")
    return tuple(normalized)


def load_policy(path: Path) -> tuple[DiffCoveragePolicy, str]:
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise ValueError(f"diff coverage policy not found: {path}") from exc
    try:
        payload: Any = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"diff coverage policy is invalid TOML: {path}") from exc
    section = payload.get("diff_coverage") if isinstance(payload, Mapping) else None
    if not isinstance(section, Mapping):
        raise ValueError("diff coverage policy requires a [diff_coverage] table")
    include_roots = _string_tuple(section.get("include_roots"), "include_roots", allow_empty=False)
    exclude = _string_tuple(section.get("exclude", []), "exclude", allow_empty=True)
    minimum = _percentage(
        section.get("minimum_changed_line_percent"),
        "minimum_changed_line_percent",
    )
    if minimum < 85:
        raise ValueError("minimum_changed_line_percent must be at least the repository 85% line floor")
    allow_none = section.get("allow_no_changed_executable_lines", True)
    if not isinstance(allow_none, bool):
        raise ValueError("allow_no_changed_executable_lines must be true or false")
    return (
        DiffCoveragePolicy(
            include_roots=include_roots,
            exclude=exclude,
            minimum_changed_line_percent=minimum,
            allow_no_changed_executable_lines=allow_none,
        ),
        hashlib.sha256(raw).hexdigest(),
    )


def _run_git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown git error"
        raise ValueError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout.strip()


def resolve_git_context(repo_root: Path, base: str, head: str) -> GitContext:
    if not base.strip():
        raise ValueError("an explicit diff coverage base ref or SHA is required")
    if not head.strip():
        raise ValueError("diff coverage head ref or SHA must not be empty")
    base_sha = _run_git(repo_root, "rev-parse", "--verify", f"{base}^{{commit}}")
    head_sha = _run_git(repo_root, "rev-parse", "--verify", f"{head}^{{commit}}")
    merge_base = _run_git(repo_root, "merge-base", base_sha, head_sha)
    if not re.fullmatch(r"[0-9a-fA-F]{40}", merge_base):
        raise ValueError("git merge-base did not return a full commit SHA")
    return GitContext(base_sha=base_sha.lower(), head_sha=head_sha.lower(), merge_base_sha=merge_base.lower())


def parse_changed_lines(diff_text: str) -> dict[str, set[int]]:
    changed: dict[str, set[int]] = {}
    current_path: str | None = None
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            current_path = None
            continue
        if line.startswith("+++ "):
            marker = line[4:].strip()
            if marker == "/dev/null":
                current_path = None
                continue
            if marker.startswith("b/"):
                marker = marker[2:]
            current_path = _normalize_path(marker)
            changed.setdefault(current_path, set())
            continue
        if not line.startswith("@@ "):
            continue
        match = _HUNK_RE.match(line)
        if match is None:
            raise ValueError(f"unsupported unified diff hunk header: {line}")
        start = int(match.group("new_start"))
        count = int(match.group("new_count") or "1")
        if count < 0:
            raise ValueError(f"invalid unified diff hunk count: {line}")
        if current_path is None:
            if count == 0:
                continue
            raise ValueError("unified diff contains a hunk before a target file header")
        if count:
            changed[current_path].update(range(start, start + count))
    return changed


def collect_changed_lines(
    repo_root: Path,
    context: GitContext,
    policy: DiffCoveragePolicy,
) -> dict[str, set[int]]:
    diff_text = _run_git(
        repo_root,
        "diff",
        "--unified=0",
        "--find-renames",
        "--find-copies",
        "--no-color",
        f"{context.merge_base_sha}..{context.head_sha}",
        "--",
        *policy.include_roots,
    )
    parsed = parse_changed_lines(diff_text)
    result: dict[str, set[int]] = {}
    for raw_path, lines in parsed.items():
        path = _normalize_path(raw_path)
        if not any(path == root or path.startswith(f"{root}/") for root in policy.include_roots):
            continue
        if any(fnmatch.fnmatch(path, pattern) for pattern in policy.exclude):
            continue
        result[path] = set(lines)
    return dict(sorted(result.items()))


def load_coverage_lines(report_path: Path, repo_root: Path) -> dict[str, tuple[set[int], set[int]]]:
    try:
        payload: Any = json.loads(report_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"coverage report not found: {report_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"coverage report is invalid JSON: {report_path}") from exc
    files = payload.get("files") if isinstance(payload, Mapping) else None
    if not isinstance(files, Mapping):
        raise ValueError("coverage report is missing an object-valued files field")
    normalized: dict[str, tuple[set[int], set[int]]] = {}
    root_text = repo_root.resolve().as_posix().rstrip("/")
    for raw_path, record in files.items():
        if not isinstance(raw_path, str) or not isinstance(record, Mapping):
            raise ValueError("coverage report contains an invalid file record")
        path = raw_path.replace("\\", "/")
        if path.startswith(f"{root_text}/"):
            path = path[len(root_text) + 1 :]
        path = _normalize_path(path)
        executed = record.get("executed_lines")
        missing = record.get("missing_lines")
        if not isinstance(executed, list) or not isinstance(missing, list):
            raise ValueError(f"coverage report lacks executable line evidence for: {path}")
        if not all(isinstance(item, int) and item > 0 for item in (*executed, *missing)):
            raise ValueError(f"coverage report has invalid line numbers for: {path}")
        if path in normalized:
            raise ValueError(f"coverage report normalizes multiple records to: {path}")
        normalized[path] = (set(executed), set(missing))
    return normalized


def evaluate(
    context: GitContext,
    policy: DiffCoveragePolicy,
    policy_sha256: str,
    changed_lines: Mapping[str, set[int]],
    coverage_lines: Mapping[str, tuple[set[int], set[int]]],
) -> DiffCoverageResult:
    files: list[FileCoverage] = []
    for path in sorted(changed_lines):
        evidence = coverage_lines.get(path)
        if evidence is None:
            raise ValueError(f"changed production file is absent from coverage evidence: {path}")
        executed, missing = evidence
        executable = set(changed_lines[path]) & (executed | missing)
        covered = executable & executed
        missed = executable & missing
        if covered | missed != executable:
            raise ValueError(f"coverage evidence is internally inconsistent for: {path}")
        files.append(
            FileCoverage(
                path=path,
                changed_lines=tuple(sorted(changed_lines[path])),
                executable_lines=tuple(sorted(executable)),
                covered_lines=tuple(sorted(covered)),
                missed_lines=tuple(sorted(missed)),
            )
        )
    return DiffCoverageResult(
        context=context,
        policy=policy,
        policy_sha256=policy_sha256,
        files=tuple(files),
    )


def result_to_dict(result: DiffCoverageResult) -> dict[str, object]:
    aggregate_percent = result.percent
    return {
        "base_sha": result.context.base_sha,
        "head_sha": result.context.head_sha,
        "merge_base_sha": result.context.merge_base_sha,
        "policy_sha256": result.policy_sha256,
        "minimum_changed_line_percent": result.policy.minimum_changed_line_percent,
        "allow_no_changed_executable_lines": result.policy.allow_no_changed_executable_lines,
        "include_roots": list(result.policy.include_roots),
        "exclude": list(result.policy.exclude),
        "files": [
            {
                "path": item.path,
                "changed_lines": list(item.changed_lines),
                "changed_executable_lines": list(item.executable_lines),
                "covered_lines": list(item.covered_lines),
                "missed_lines": list(item.missed_lines),
                "percent": item.percent,
            }
            for item in result.files
        ],
        "summary": {
            "changed_executable_lines": result.executable_line_count,
            "covered_lines": result.covered_line_count,
            "missed_lines": result.missed_line_count,
            "percent": aggregate_percent,
            "result": "pass" if result.passed else "fail",
        },
    }


def render_markdown(result: DiffCoverageResult) -> str:
    percent = "not applicable" if result.percent is None else f"{result.percent:.2f}%"
    lines = [
        "## Changed-production-line coverage",
        "",
        f"- Base SHA: `{result.context.base_sha}`",
        f"- Head SHA: `{result.context.head_sha}`",
        f"- Merge base: `{result.context.merge_base_sha}`",
        f"- Policy SHA-256: `{result.policy_sha256}`",
        f"- Required changed-line floor: {result.policy.minimum_changed_line_percent:.2f}%",
        f"- Changed executable lines: {result.executable_line_count}",
        f"- Covered changed executable lines: {result.covered_line_count}",
        f"- Missed changed executable lines: {result.missed_line_count}",
        f"- Aggregate changed-line coverage: {percent}",
        f"- Result: **{'PASS' if result.passed else 'FAIL'}**",
        "",
        "| File | Changed executable | Covered | Missed | Coverage |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for item in result.files:
        item_percent = "not applicable" if item.percent is None else f"{item.percent:.2f}%"
        missed = "—" if not item.missed_lines else ", ".join(str(line) for line in item.missed_lines)
        lines.append(
            f"| `{item.path}` | {len(item.executable_lines)} | {len(item.covered_lines)} | "
            f"{missed} | {item_percent} |"
        )
    if not result.files:
        lines.append("| _No configured production files changed_ | 0 | 0 | — | not applicable |")
    lines.append("")
    return "\n".join(lines)


def write_evidence(result: DiffCoverageResult, json_output: Path | None, markdown_output: Path | None) -> None:
    if json_output is not None:
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(json.dumps(result_to_dict(result), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if markdown_output is not None:
        markdown_output.parent.mkdir(parents=True, exist_ok=True)
        markdown_output.write_text(render_markdown(result), encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", nargs="?", type=Path, default=Path("coverage.json"))
    parser.add_argument("--base", required=True, help="Explicit base ref or SHA")
    parser.add_argument("--head", default="HEAD", help="Head ref or SHA (default: HEAD)")
    parser.add_argument("--config", type=Path, default=Path("config/diff-coverage.toml"))
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo_root = args.repo_root.resolve()
    try:
        policy, policy_sha256 = load_policy(args.config)
        context = resolve_git_context(repo_root, args.base, args.head)
        changed = collect_changed_lines(repo_root, context, policy)
        coverage = load_coverage_lines(args.report, repo_root)
        result = evaluate(context, policy, policy_sha256, changed, coverage)
        write_evidence(result, args.json_output, args.markdown_output)
    except ValueError as exc:
        print(f"diff coverage error: {exc}", file=sys.stderr)
        return 2
    print(render_markdown(result))
    if not result.passed:
        print(
            f"changed-line coverage missed the {policy.minimum_changed_line_percent:.2f}% policy floor",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
