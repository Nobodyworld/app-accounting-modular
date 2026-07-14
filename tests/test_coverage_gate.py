"""Tests for durable line and branch coverage evidence handling."""

from __future__ import annotations

import json
from pathlib import Path

from src.tools.coverage_gate import (
    CoverageSummary,
    load_coverage_summary,
    main,
    render_markdown,
)


def _write_report(
    tmp_path: Path,
    *,
    covered_lines: int = 90,
    total_lines: int = 100,
    covered_branches: int = 30,
    total_branches: int = 40,
) -> Path:
    report = tmp_path / "coverage.json"
    report.write_text(
        json.dumps(
            {
                "files": {
                    "src/apps/example.py": {},
                    "src/cli/example.py": {},
                },
                "totals": {
                    "covered_lines": covered_lines,
                    "num_statements": total_lines,
                    "covered_branches": covered_branches,
                    "num_branches": total_branches,
                },
            }
        ),
        encoding="utf-8",
    )
    return report


def test_load_coverage_summary_normalizes_line_and_branch_totals(
    tmp_path: Path,
) -> None:
    report = _write_report(tmp_path)

    summary = load_coverage_summary(report)

    assert summary == CoverageSummary(
        covered_lines=90,
        total_lines=100,
        covered_branches=30,
        total_branches=40,
        file_count=2,
    )
    assert summary.line_percent == 90.0
    assert summary.branch_percent == 75.0


def test_render_markdown_distinguishes_line_gate_from_branch_evidence() -> None:
    summary = CoverageSummary(
        covered_lines=86,
        total_lines=100,
        covered_branches=60,
        total_branches=100,
        file_count=3,
    )

    rendered = render_markdown(summary, 85.0)

    assert "Release-authoritative line coverage | 86.00%" in rendered
    assert "Branch coverage evidence | 60.00%" in rendered
    assert "Line gate | **PASS**" in rendered


def test_main_passes_and_appends_github_step_summary(
    tmp_path: Path, monkeypatch
) -> None:
    report = _write_report(tmp_path, covered_lines=85, total_lines=100)
    step_summary = tmp_path / "step-summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(step_summary))

    exit_code = main([str(report), "--minimum-line", "85"])

    assert exit_code == 0
    summary_text = step_summary.read_text(encoding="utf-8")
    assert "Line gate | **PASS**" in summary_text
    assert "85.00% (85/100 lines)" in summary_text


def test_main_fails_when_line_coverage_is_below_floor(tmp_path: Path) -> None:
    report = _write_report(tmp_path, covered_lines=84, total_lines=100)

    assert main([str(report), "--minimum-line", "85"]) == 1


def test_main_rejects_missing_or_invalid_reports(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    assert main([str(missing)]) == 2

    invalid = tmp_path / "invalid.json"
    invalid.write_text("[]", encoding="utf-8")
    assert main([str(invalid)]) == 2


def test_summary_without_branches_reports_no_branch_percentage() -> None:
    summary = CoverageSummary(
        covered_lines=1,
        total_lines=1,
        covered_branches=0,
        total_branches=0,
        file_count=1,
    )

    assert summary.branch_percent is None
    assert "not measured" in render_markdown(summary, 85.0)
