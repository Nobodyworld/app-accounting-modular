"""Fail closed when a configured critical module misses its coverage floor."""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class CriticalModule:
    path: str
    line_floor: float
    branch_floor: float | None


@dataclass(frozen=True, slots=True)
class ModuleResult:
    module: CriticalModule
    line_percent: float
    branch_percent: float | None

    @property
    def passed(self) -> bool:
        if self.line_percent < self.module.line_floor:
            return False
        if self.module.branch_floor is not None:
            return self.branch_percent is not None and self.branch_percent >= self.module.branch_floor
        return True


def _percent(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    result = float(value)
    if not 0 <= result <= 100:
        raise ValueError(f"{label} must be between 0 and 100")
    return result


def load_policy(path: Path) -> tuple[CriticalModule, ...]:
    try:
        payload: Any = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"critical coverage policy not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"critical coverage policy is invalid TOML: {path}") from exc
    entries = payload.get("module") if isinstance(payload, Mapping) else None
    if not isinstance(entries, list) or not entries:
        raise ValueError("critical coverage policy requires at least one [[module]] entry")
    modules: list[CriticalModule] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            raise ValueError(f"module entry {index + 1} must be an object")
        raw_path = entry.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError(f"module entry {index + 1} requires a nonempty path")
        normalized = raw_path.strip().replace("\\", "/")
        if normalized in seen:
            raise ValueError(f"duplicate critical module path: {normalized}")
        seen.add(normalized)
        branch_value = entry.get("branch_floor")
        modules.append(
            CriticalModule(
                path=normalized,
                line_floor=_percent(entry.get("line_floor"), f"{normalized} line_floor"),
                branch_floor=(
                    _percent(branch_value, f"{normalized} branch_floor") if branch_value is not None else None
                ),
            )
        )
    return tuple(modules)


def evaluate(report_path: Path, modules: Sequence[CriticalModule]) -> tuple[ModuleResult, ...]:
    try:
        payload: Any = json.loads(report_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"coverage report not found: {report_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"coverage report is invalid JSON: {report_path}") from exc
    files = payload.get("files") if isinstance(payload, Mapping) else None
    if not isinstance(files, Mapping):
        raise ValueError("coverage report is missing an object-valued files field")
    normalized_files = {str(path).replace("\\", "/"): value for path, value in files.items()}
    results: list[ModuleResult] = []
    for module in modules:
        record = normalized_files.get(module.path)
        if not isinstance(record, Mapping):
            raise ValueError(f"critical module missing from coverage report: {module.path}")
        summary = record.get("summary")
        if not isinstance(summary, Mapping):
            raise ValueError(f"critical module is missing coverage summary: {module.path}")
        statements = summary.get("num_statements")
        covered_lines = summary.get("covered_lines")
        if not isinstance(statements, int) or not isinstance(covered_lines, int) or statements < 0:
            raise ValueError(f"critical module has invalid line evidence: {module.path}")
        line_percent = 100.0 if statements == 0 else covered_lines / statements * 100
        branches = summary.get("num_branches")
        covered_branches = summary.get("covered_branches")
        branch_percent: float | None = None
        if isinstance(branches, int) and isinstance(covered_branches, int) and branches > 0:
            branch_percent = covered_branches / branches * 100
        if module.branch_floor is not None and branch_percent is None:
            raise ValueError(f"critical module is missing branch evidence: {module.path}")
        results.append(ModuleResult(module, line_percent, branch_percent))
    return tuple(results)


def render(results: Sequence[ModuleResult]) -> str:
    lines = [
        "## Critical-module coverage",
        "",
        "| Module | Lines | Floor | Branches | Floor | Result |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for result in results:
        branch = "not configured" if result.branch_percent is None else f"{result.branch_percent:.2f}%"
        branch_floor = "—" if result.module.branch_floor is None else f"{result.module.branch_floor:.2f}%"
        lines.append(
            f"| `{result.module.path}` | {result.line_percent:.2f}% | {result.module.line_floor:.2f}% | "
            f"{branch} | {branch_floor} | {'PASS' if result.passed else 'FAIL'} |"
        )
    lines.append("")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", nargs="?", type=Path, default=Path("coverage.json"))
    parser.add_argument("--config", type=Path, default=Path("config/critical-coverage.toml"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        results = evaluate(args.report, load_policy(args.config))
    except ValueError as exc:
        print(f"critical coverage error: {exc}", file=sys.stderr)
        return 2
    print(render(results))
    failures = [result for result in results if not result.passed]
    if failures:
        print(f"{len(failures)} critical module(s) missed their configured floor", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
