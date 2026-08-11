from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from src.tools.diff_coverage import (
    DiffCoveragePolicy,
    GitContext,
    _normalize_path,
    collect_changed_lines,
    evaluate,
    load_coverage_lines,
    load_policy,
    parse_changed_lines,
    render_markdown,
    resolve_git_context,
    result_to_dict,
    write_evidence,
)


def _policy() -> DiffCoveragePolicy:
    return DiffCoveragePolicy(
        include_roots=("src/apps", "src/plugins", "src/cli"),
        exclude=(),
        minimum_changed_line_percent=85.0,
    )


def _context() -> GitContext:
    return GitContext(base_sha="a" * 40, head_sha="b" * 40, merge_base_sha="c" * 40)


def test_load_policy_requires_explicit_roots_and_floor(tmp_path: Path) -> None:
    policy_path = tmp_path / "diff.toml"
    policy_path.write_text(
        "\n".join(
            [
                "[diff_coverage]",
                'include_roots = ["src/apps", "src/plugins"]',
                'exclude = ["src/apps/generated/**"]',
                "minimum_changed_line_percent = 90",
                "allow_no_changed_executable_lines = true",
                "",
            ]
        ),
        encoding="utf-8",
    )

    policy, fingerprint = load_policy(policy_path)

    assert policy == DiffCoveragePolicy(
        include_roots=("src/apps", "src/plugins"),
        exclude=("src/apps/generated/**",),
        minimum_changed_line_percent=90.0,
        allow_no_changed_executable_lines=True,
    )
    assert len(fingerprint) == 64

    policy_path.write_text(
        '[diff_coverage]\ninclude_roots=["src/apps"]\nminimum_changed_line_percent=84.99\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="at least the repository 85% line floor"):
        load_policy(policy_path)


def test_parse_changed_lines_handles_modified_new_renamed_and_deleted_files() -> None:
    diff = "\n".join(
        [
            "diff --git a/src/apps/a.py b/src/apps/a.py",
            "--- a/src/apps/a.py",
            "+++ b/src/apps/a.py",
            "@@ -2,2 +2,3 @@",
            "diff --git a/src/apps/new.py b/src/apps/new.py",
            "new file mode 100644",
            "--- /dev/null",
            "+++ b/src/apps/new.py",
            "@@ -0,0 +1,2 @@",
            "diff --git a/src/apps/old.py b/src/apps/renamed.py",
            "similarity index 80%",
            "rename from src/apps/old.py",
            "rename to src/apps/renamed.py",
            "--- a/src/apps/old.py",
            "+++ b/src/apps/renamed.py",
            "@@ -5 +5 @@",
            "diff --git a/src/apps/deleted.py b/src/apps/deleted.py",
            "deleted file mode 100644",
            "--- a/src/apps/deleted.py",
            "+++ /dev/null",
            "@@ -1,2 +0,0 @@",
        ]
    )

    assert parse_changed_lines(diff) == {
        "src/apps/a.py": {2, 3, 4},
        "src/apps/new.py": {1, 2},
        "src/apps/renamed.py": {5},
    }


def test_parse_changed_lines_rejects_malformed_hunk() -> None:
    with pytest.raises(ValueError, match="unsupported unified diff"):
        parse_changed_lines("+++ b/src/apps/a.py\n@@ malformed @@")


def test_evaluate_reports_covered_and_missed_changed_executable_lines() -> None:
    result = evaluate(
        _context(),
        _policy(),
        "d" * 64,
        {
            "src/apps/a.py": {1, 2, 3, 4},
            "src/plugins/b.py": {8, 9},
        },
        {
            "src/apps/a.py": ({1, 2, 10}, {3, 11}),
            "src/plugins/b.py": ({8}, {9}),
        },
    )

    assert result.executable_line_count == 5
    assert result.covered_line_count == 3
    assert result.missed_line_count == 2
    assert result.percent == pytest.approx(60.0)
    assert result.passed is False
    assert result.files[0].missed_lines == (3,)
    assert result.files[1].missed_lines == (9,)

    payload = result_to_dict(result)
    assert payload["summary"] == {
        "changed_executable_lines": 5,
        "covered_lines": 3,
        "missed_lines": 2,
        "percent": 60.0,
        "result": "fail",
    }
    markdown = render_markdown(result)
    assert "`src/apps/a.py`" in markdown
    assert "| 3 | 2 | 3 | 66.67% |" in markdown
    assert "Result: **FAIL**" in markdown


def test_no_changed_executable_lines_is_an_explicit_pass() -> None:
    result = evaluate(
        _context(),
        _policy(),
        "d" * 64,
        {"src/apps/a.py": {1, 2}},
        {"src/apps/a.py": ({10}, {11})},
    )

    assert result.executable_line_count == 0
    assert result.percent is None
    assert result.passed is True
    assert "not applicable" in render_markdown(result)


def test_changed_production_file_missing_from_coverage_fails_closed() -> None:
    with pytest.raises(ValueError, match="absent from coverage evidence"):
        evaluate(
            _context(),
            _policy(),
            "d" * 64,
            {"src/apps/new.py": {1}},
            {},
        )


def test_load_coverage_lines_normalizes_posix_windows_and_absolute_paths(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    report = tmp_path / "coverage.json"
    absolute = (repo_root / "src" / "apps" / "absolute.py").as_posix()
    report.write_text(
        json.dumps(
            {
                "files": {
                    "src\\apps\\windows.py": {"executed_lines": [1], "missing_lines": [2]},
                    absolute: {"executed_lines": [3], "missing_lines": []},
                }
            }
        ),
        encoding="utf-8",
    )

    evidence = load_coverage_lines(report, repo_root)

    assert evidence == {
        "src/apps/windows.py": ({1}, {2}),
        "src/apps/absolute.py": ({3}, set()),
    }
    assert _normalize_path(".\\src\\apps\\example.py") == "src/apps/example.py"


def test_load_coverage_lines_rejects_malformed_reports(tmp_path: Path) -> None:
    report = tmp_path / "coverage.json"
    report.write_text("not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON"):
        load_coverage_lines(report, tmp_path)

    report.write_text('{"files":{"src/apps/a.py":{"summary":{}}}}', encoding="utf-8")
    with pytest.raises(ValueError, match="lacks executable line evidence"):
        load_coverage_lines(report, tmp_path)


def test_write_evidence_is_deterministic(tmp_path: Path) -> None:
    result = evaluate(
        _context(),
        _policy(),
        "d" * 64,
        {"src/apps/a.py": {3, 1, 2}},
        {"src/apps/a.py": ({1, 3}, {2})},
    )
    json_path = tmp_path / "diff.json"
    markdown_path = tmp_path / "diff.md"

    write_evidence(result, json_path, markdown_path)
    first_json = json_path.read_bytes()
    first_markdown = markdown_path.read_bytes()
    write_evidence(result, json_path, markdown_path)

    assert json_path.read_bytes() == first_json
    assert markdown_path.read_bytes() == first_markdown
    assert first_json.endswith(b"\n")
    assert first_markdown.endswith(b"\n")


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def test_git_context_and_changed_lines_use_merge_base(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "diff-coverage@example.invalid")
    _git(repo, "config", "user.name", "Diff Coverage Test")
    source = repo / "src" / "apps" / "example.py"
    source.parent.mkdir(parents=True)
    source.write_text("value = 1\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    base_sha = _git(repo, "rev-parse", "HEAD")
    source.write_text("value = 2\nother = 3\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "head")

    context = resolve_git_context(repo, base_sha, "HEAD")
    changed = collect_changed_lines(repo, context, _policy())

    assert context.base_sha == base_sha
    assert context.merge_base_sha == base_sha
    assert changed == {"src/apps/example.py": {1, 2}}

    with pytest.raises(ValueError, match="rev-parse"):
        resolve_git_context(repo, "missing-base", "HEAD")


def test_diff_coverage_workflow_uses_exact_pr_base_and_uploads_evidence() -> None:
    workflow = Path(".github/workflows/diff-coverage.yml").read_text(encoding="utf-8")

    assert "github.event.pull_request.base.sha" in workflow
    assert "github.event.pull_request.head.sha" in workflow
    assert "persist-credentials: false" in workflow
    assert "fetch-depth: 0" in workflow
    assert "diff-coverage.json" in workflow
    assert "diff-coverage.md" in workflow
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in workflow
    assert "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97" in workflow
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in workflow
