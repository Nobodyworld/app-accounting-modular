"""Collect repository health metrics for steward reports and automation."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

PROJECT_PREFIXES: tuple[str, ...] = ("apps", "cli", "plugins", "tools")


@dataclass(slots=True)
class CommandResult:
    """Summary of a subprocess execution."""

    command: tuple[str, ...]
    returncode: int
    duration: float


def _run_command(*args: str, raise_on_error: bool = True) -> CommandResult:
    start = time.perf_counter()
    try:
        completed = subprocess.run(args, check=raise_on_error)
        returncode = completed.returncode
    except subprocess.CalledProcessError as exc:
        if raise_on_error:
            raise
        completed = exc
        returncode = exc.returncode
    duration = time.perf_counter() - start
    return CommandResult(command=tuple(args), returncode=returncode, duration=duration)


def _collect_pytest(skip: bool) -> CommandResult | None:
    if skip:
        return None
    return _run_command(sys.executable, "-m", "pytest")


def _collect_trace(trace_dir: Path, skip: bool) -> CommandResult | None:
    if skip:
        return None
    if trace_dir.exists():
        shutil.rmtree(trace_dir)
    trace_dir.mkdir(parents=True, exist_ok=True)
    return _run_command(
        sys.executable,
        "-m",
        "trace",
        "--count",
        "--coverdir",
        str(trace_dir),
        "--module",
        "pytest",
        raise_on_error=False,
    )


def _parse_cover_file(path: Path) -> tuple[int, int]:
    executed = 0
    missing = 0
    pattern = re.compile(r"^\s*\d+\s*:")
    with path.open() as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\n")
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if pattern.match(line):
                executed += 1
            else:
                missing += 1
    return executed, missing


def _aggregate_coverage(trace_dir: Path, prefixes: Mapping[str, str]) -> dict[str, dict[str, float]]:
    results: dict[str, dict[str, float]] = {}
    for display, prefix in prefixes.items():
        executed = 0
        missing = 0
        for cover_file in trace_dir.glob("*.cover"):
            module_path = cover_file.stem.replace(".", "/")
            if not module_path.startswith(prefix):
                continue
            hit, miss = _parse_cover_file(cover_file)
            executed += hit
            missing += miss
        total = executed + missing
        percentage = (executed / total * 100) if total else 0.0
        results[display] = {
            "executed": executed,
            "missing": missing,
            "coverage_percent": round(percentage, 2),
        }
    return results


def _measure_package_size(paths: Iterable[Path]) -> dict[str, float]:
    sizes: dict[str, float] = {}
    for path in paths:
        total = 0
        for file in path.rglob("*.py"):
            total += file.stat().st_size
        sizes[path.name] = round(total / 1024, 1)
    return sizes


def _compute_complexity(modules: Iterable[Path]) -> dict[str, dict[str, float]]:
    import ast

    class ComplexityVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.complexity = 0

        def generic_visit(self, node):  # type: ignore[override]
            if isinstance(
                node,
                ast.If | ast.For | ast.While | ast.With | ast.AsyncWith | ast.Try | ast.Match,
            ):
                self.complexity += 1
            elif isinstance(node, ast.BoolOp):
                self.complexity += max(len(node.values) - 1, 1)
            elif isinstance(node, ast.comprehension):
                self.complexity += 1
            super().generic_visit(node)

    def _scores(path: Path) -> list[float]:
        tree = ast.parse(path.read_text())
        scores: list[float] = []
        for node in tree.body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                visitor = ComplexityVisitor()
                visitor.visit(node)
                scores.append(1 + visitor.complexity)
        return scores

    results: dict[str, dict[str, float]] = {}
    for module in modules:
        scores = _scores(module)
        if not scores:
            continue
        results[module.as_posix()] = {
            "average": round(mean(scores), 2),
            "max": max(scores),
        }
    return results


def _dependency_profile(modules: Iterable[Path]) -> dict[str, dict[str, float]]:
    import ast

    profiles: dict[str, dict[str, float]] = {}
    for module in modules:
        tree = ast.parse(module.read_text())
        internal = 0
        external = 0
        unique: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    unique.add(name)
                    if name.startswith(PROJECT_PREFIXES):
                        internal += 1
                    else:
                        external += 1
            elif isinstance(node, ast.ImportFrom):
                module_name = node.module or ""
                unique.add(module_name)
                if module_name.startswith(PROJECT_PREFIXES) or node.level:
                    internal += 1
                else:
                    external += 1
        total = internal + external
        ratio = (internal / total) if total else 0.0
        profiles[module.as_posix()] = {
            "internal": internal,
            "external": external,
            "internal_ratio": round(ratio, 2),
            "unique_dependencies": len(unique),
        }
    return profiles


def _render_markdown(metrics: Mapping[str, object]) -> str:
    coverage = metrics.get("coverage", {})
    lines = ["| Package | Coverage | Executed | Missing |", "| --- | --- | --- | --- |"]
    for name, values in coverage.items():
        pct = values.get("coverage_percent", 0)
        executed = values.get("executed", 0)
        missing = values.get("missing", 0)
        lines.append(f"| {name} | {pct:.2f}% | {executed} | {missing} |")
    return "\n".join(lines)


# agent-entrypoint
def main(argv: list[str] | None = None) -> int:
    """Execute the audit workflow and print metrics in the requested format."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-dir", type=Path, default=Path("docs/reports/tracecov"))
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip the initial pytest run when only coverage metrics are needed.",
    )
    parser.add_argument(
        "--skip-trace",
        action="store_true",
        help="Skip the trace-based coverage run (coverage data will be empty).",
    )
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="Output format for metrics.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional file path to write the rendered metrics.",
    )
    args = parser.parse_args(argv)

    metrics: dict[str, object] = {}

    pytest_result = _collect_pytest(args.skip_tests)
    if pytest_result is not None:
        metrics["pytest_runtime_seconds"] = round(pytest_result.duration, 2)

    trace_result = _collect_trace(args.trace_dir, args.skip_trace)
    if trace_result is not None:
        metrics["trace_runtime_seconds"] = round(trace_result.duration, 2)
        metrics["coverage"] = _aggregate_coverage(
            args.trace_dir,
            {"apps": "apps/", "cli": "cli/", "plugins": "plugins/"},
        )
    else:
        if args.trace_dir.exists():
            metrics["coverage"] = _aggregate_coverage(
                args.trace_dir,
                {"apps": "apps/", "cli": "cli/", "plugins": "plugins/"},
            )
        else:
            metrics["coverage"] = {}

    target_modules = [
        Path("src/cli/macli.py"),
        Path("src/apps/modular_accounting/application/snapshots.py"),
        Path("src/apps/observability/tracing.py"),
        Path("src/apps/extensions/scaffold.py"),
    ]
    metrics["complexity"] = _compute_complexity(target_modules)
    metrics["dependencies"] = _dependency_profile(target_modules)
    metrics["package_sizes_kb"] = _measure_package_size(Path(name) for name in ("apps", "cli", "plugins"))

    if args.format == "markdown":
        rendered = _render_markdown(metrics)
    else:
        rendered = json.dumps(metrics, indent=2, sort_keys=True)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n")
    print(rendered)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI hook
    raise SystemExit(main())
