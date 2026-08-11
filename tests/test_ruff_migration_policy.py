from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

from src.tools.quality_gate import COMMANDS

REPO_ROOT = Path(__file__).resolve().parents[1]


def _pyproject() -> dict[str, object]:
    return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_ruff_requirement_is_exactly_0160() -> None:
    requirements = (REPO_ROOT / "requirements-dev.txt").read_text(encoding="utf-8").splitlines()
    ruff_requirements = [line for line in requirements if line.strip().lower().startswith("ruff")]

    assert ruff_requirements == ["ruff==0.16.0"]

    result = subprocess.run(
        [sys.executable, "-m", "ruff", "--version"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ruff 0.16.0"


def test_ruff_rule_selection_and_discovery_are_explicit() -> None:
    config = _pyproject()["tool"]["ruff"]  # type: ignore[index]
    lint = config["lint"]  # type: ignore[index]
    formatter = config["format"]  # type: ignore[index]

    assert config["include"] == ["*.py", "*.pyi", "pyproject.toml"]  # type: ignore[index]
    assert config["extend-exclude"] == ["*.md", "*.ipynb"]  # type: ignore[index]
    assert config["force-exclude"] is True  # type: ignore[index]
    assert config["respect-gitignore"] is True  # type: ignore[index]

    assert lint["select"] == ["E", "F", "I", "UP", "B"]  # type: ignore[index]
    assert lint["ignore"] == ["B008"]  # type: ignore[index]
    assert lint["preview"] is False  # type: ignore[index]

    assert formatter["preview"] is False  # type: ignore[index]
    assert formatter["docstring-code-format"] is False  # type: ignore[index]


def test_quality_gate_keeps_config_driven_ruff_commands() -> None:
    commands = {tuple(command) for command in COMMANDS}

    assert (sys.executable, "-m", "ruff", "check", ".") in commands
    assert (sys.executable, "-m", "ruff", "format", "--check", ".") in commands


def test_markdown_is_excluded_but_python_is_formatted(tmp_path: Path) -> None:
    markdown = tmp_path / "example.md"
    markdown.write_text("```python\nvalue=  1\n```\n", encoding="utf-8")

    markdown_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--check",
            "--config",
            str(REPO_ROOT / "pyproject.toml"),
            str(markdown),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert markdown_result.returncode == 0, markdown_result.stdout + markdown_result.stderr

    python_file = tmp_path / "example.py"
    python_file.write_text("value=  1\n", encoding="utf-8")

    python_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--check",
            "--config",
            str(REPO_ROOT / "pyproject.toml"),
            str(python_file),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert python_result.returncode == 1
    assert "Would reformat" in python_result.stdout + python_result.stderr
