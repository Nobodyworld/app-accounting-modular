"""Validate line coverage from a pytest-cov JSON report and summarize branch evidence."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_REPORT = Path("coverage.json")
DEFAULT_MINIMUM_LINE_PERCENT = 85.0


@dataclass(frozen=True, slots=True)
class CoverageSummary:
    """Normalized line and branch totals from a coverage.py JSON report."""

    covered_lines: int
    total_lines: int
    covered_branches: int
    total_branches: int
    file_count: int

    @property
    def line_percent(self) -> float:
        """Return line coverage as a percentage."""

        if self.total_lines == 0:
            return 100.0
        return self.covered_lines / self.total_lines * 100.0

    @property
    def branch_percent(self) -> float | None:
        """Return branch coverage as a percentage when branch data exists."""

        if self.total_branches == 0:
            return None
        return self.covered_branches / self.total_branches * 100.0


def _nonnegative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(
            f"coverage totals field '{field_name}' must be a non-negative integer"
        )
    return value


def load_coverage_summary(report_path: Path) -> CoverageSummary:
    """Load and validate the totals needed for the release-authoritative line gate."""

    try:
        payload: Any = json.loads(report_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"coverage report not found: {report_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"coverage report is not valid JSON: {report_path}") from exc

    if not isinstance(payload, Mapping):
        raise ValueError("coverage report root must be an object")

    totals = payload.get("totals")
    if not isinstance(totals, Mapping):
        raise ValueError("coverage report is missing an object-valued 'totals' field")

    files = payload.get("files", {})
    if not isinstance(files, Mapping):
        raise ValueError("coverage report 'files' field must be an object")

    covered_lines = _nonnegative_int(totals.get("covered_lines"), "covered_lines")
    total_lines = _nonnegative_int(totals.get("num_statements"), "num_statements")
    covered_branches = _nonnegative_int(
        totals.get("covered_branches", 0), "covered_branches"
    )
    total_branches = _nonnegative_int(totals.get("num_branches", 0), "num_branches")

    if covered_lines > total_lines:
        raise ValueError("covered_lines cannot exceed num_statements")
    if covered_branches > total_branches:
        raise ValueError("covered_branches cannot exceed num_branches")

    return CoverageSummary(
        covered_lines=covered_lines,
        total_lines=total_lines,
        covered_branches=covered_branches,
        total_branches=total_branches,
        file_count=len(files),
    )


def render_markdown(summary: CoverageSummary, minimum_line_percent: float) -> str:
    """Render a concise GitHub Actions step summary."""

    branch_display = "not measured"
    if summary.branch_percent is not None:
        branch_display = (
            f"{summary.branch_percent:.2f}% "
            f"({summary.covered_branches}/{summary.total_branches} branches)"
        )

    status = "PASS" if summary.line_percent >= minimum_line_percent else "FAIL"
    return "\n".join(
        [
            "## Coverage evidence",
            "",
            "| Metric | Result |",
            "| --- | ---: |",
            (
                f"| Release-authoritative line coverage | {summary.line_percent:.2f}% "
                f"({summary.covered_lines}/{summary.total_lines} lines) |"
            ),
            f"| Required line floor | {minimum_line_percent:.2f}% |",
            f"| Branch coverage evidence | {branch_display} |",
            f"| Files represented | {summary.file_count} |",
            f"| Line gate | **{status}** |",
            "",
            "The line floor remains the release gate. Branch coverage is preserved as diagnostic evidence.",
            "",
        ]
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "report",
        nargs="?",
        type=Path,
        default=DEFAULT_REPORT,
        help="coverage.py JSON report path (default: coverage.json)",
    )
    parser.add_argument(
        "--minimum-line",
        type=float,
        default=DEFAULT_MINIMUM_LINE_PERCENT,
        help="minimum accepted line coverage percentage",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Validate the configured line floor and emit durable coverage evidence."""

    args = _parser().parse_args(argv)
    minimum_line_percent = float(args.minimum_line)
    if not 0.0 <= minimum_line_percent <= 100.0:
        print("coverage minimum must be between 0 and 100", file=sys.stderr)
        return 2

    try:
        summary = load_coverage_summary(args.report)
    except ValueError as exc:
        print(f"coverage gate error: {exc}", file=sys.stderr)
        return 2

    markdown = render_markdown(summary, minimum_line_percent)
    print(markdown)

    step_summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary_path:
        with Path(step_summary_path).open("a", encoding="utf-8") as handle:
            handle.write(markdown)

    if summary.line_percent < minimum_line_percent:
        print(
            f"line coverage {summary.line_percent:.2f}% is below the required "
            f"{minimum_line_percent:.2f}%",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
