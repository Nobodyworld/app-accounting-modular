"""Release automation helpers for preparing changelog and notes."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Sequence

CHANGELOG_PATH = Path("CHANGELOG.md")
RELEASE_NOTES_PATH = Path("RELEASE_NOTES.md")


@dataclass(slots=True)
class ReleasePlan:
    version: str
    date: str
    changelog_entries: list[str]


def _extract_unreleased(lines: list[str]) -> tuple[list[str], int, int]:
    start = None
    end = len(lines)
    for idx, line in enumerate(lines):
        if line.strip() == "## Unreleased":
            start = idx + 1
            continue
        if start is not None and line.startswith("## "):
            end = idx
            break
    if start is None:
        raise RuntimeError("CHANGELOG.md missing '## Unreleased' heading")
    return lines[start:end], start, end


def plan_release(version: str, *, today: str | None = None) -> ReleasePlan:
    lines = CHANGELOG_PATH.read_text(encoding="utf-8").splitlines()
    entries, start, end = _extract_unreleased(lines)
    trimmed = [entry for entry in entries if entry.strip()]
    if not trimmed:
        raise RuntimeError("No unreleased entries to release")
    return ReleasePlan(version=version, date=today or date.today().isoformat(), changelog_entries=entries)


def update_changelog(plan: ReleasePlan) -> None:
    lines = CHANGELOG_PATH.read_text(encoding="utf-8").splitlines()
    entries, start, end = _extract_unreleased(lines)
    lines[start:end] = [""]
    release_section = [
        f"## v{plan.version} - {plan.date}",
        *entries,
    ]
    insert_at = end + 1
    lines[insert_at:insert_at] = ["", *release_section]
    CHANGELOG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_release_notes(plan: ReleasePlan) -> None:
    existing = RELEASE_NOTES_PATH.read_text(encoding="utf-8").rstrip()
    section = [
        f"## Version {plan.version} ({plan.date})",
        "- See CHANGELOG.md for detailed entries.",
    ]
    payload = existing + "\n\n" + "\n".join(section) + "\n"
    RELEASE_NOTES_PATH.write_text(payload, encoding="utf-8")


def prepare_release(version: str, *, today: str | None = None) -> None:
    plan = plan_release(version, today=today)
    update_changelog(plan)
    update_release_notes(plan)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare release collateral")
    parser.add_argument("version", help="Semantic version to release")
    parser.add_argument("--date", dest="date", help="Override release date (YYYY-MM-DD)")
    args = parser.parse_args(argv)
    prepare_release(args.version, today=args.date)
    return 0


if __name__ == "__main__":  # pragma: no cover - manual invocation
    raise SystemExit(main())
