from __future__ import annotations

import json
from pathlib import Path

import pytest
from src.tools.critical_coverage import CriticalModule, evaluate, load_policy, render


def test_policy_parser_and_actionable_failure(tmp_path: Path) -> None:
    config = tmp_path / "critical.toml"
    config.write_text(
        '[[module]]\npath="src/apps/api/example.py"\nline_floor=85\nbranch_floor=70\n',
        encoding="utf-8",
    )
    modules = load_policy(config)
    assert modules == (CriticalModule("src/apps/api/example.py", 85.0, 70.0),)
    report = tmp_path / "coverage.json"
    report.write_text(
        json.dumps(
            {
                "files": {
                    "src\\apps\\api\\example.py": {
                        "summary": {
                            "covered_lines": 8,
                            "num_statements": 10,
                            "covered_branches": 6,
                            "num_branches": 10,
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    results = evaluate(report, modules)
    assert not results[0].passed
    assert "80.00%" in render(results)
    assert "FAIL" in render(results)


def test_missing_module_and_branch_evidence_fail_closed(tmp_path: Path) -> None:
    report = tmp_path / "coverage.json"
    report.write_text('{"files": {}}', encoding="utf-8")
    module = CriticalModule("missing.py", 85.0, 70.0)
    with pytest.raises(ValueError, match="missing from coverage"):
        evaluate(report, [module])

    report.write_text('{"files":{"missing.py":{"summary":{"covered_lines":1,"num_statements":1}}}}', encoding="utf-8")
    with pytest.raises(ValueError, match="missing branch evidence"):
        evaluate(report, [module])
