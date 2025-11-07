"""Utility helpers for managing version bumps and release collateral."""

from __future__ import annotations

import argparse
import datetime as _dt
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION"
CHANGELOG_FILE = ROOT / "CHANGELOG.md"
RELEASE_NOTES_FILE = ROOT / "RELEASE_NOTES.md"


def _read_version() -> tuple[int, int, int]:
    raw = VERSION_FILE.read_text(encoding="utf-8").strip()
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", raw)
    if not match:  # pragma: no cover - defensive programming
        raise ValueError(f"Unsupported version format: {raw!r}")
    return tuple(int(group) for group in match.groups())  # type: ignore[return-value]


def _write_version(version: tuple[int, int, int]) -> str:
    payload = ".".join(str(part) for part in version)
    VERSION_FILE.write_text(f"{payload}\n", encoding="utf-8")
    return payload


def _insert_changelog_entry(version: str, message: str, *, date: str) -> None:
    lines = CHANGELOG_FILE.read_text(encoding="utf-8").splitlines()
    try:
        index = lines.index("## Unreleased")
    except ValueError as exc:  # pragma: no cover - repository invariant
        raise RuntimeError("CHANGELOG.md must contain a '## Unreleased' heading") from exc

    insertion = f"- {date} (v{version}): {message}"
    lines.insert(index + 2, insertion)
    CHANGELOG_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _insert_release_note(version: str, message: str) -> None:
    lines = RELEASE_NOTES_FILE.read_text(encoding="utf-8").splitlines()
    try:
        index = lines.index("## Highlights")
    except ValueError as exc:  # pragma: no cover - repository invariant
        raise RuntimeError("RELEASE_NOTES.md must contain a '## Highlights' heading") from exc

    highlight = f"- (v{version}) {message}"
    lines.insert(index + 1, highlight)
    RELEASE_NOTES_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def bump_version(part: str, message: str) -> str:
    major, minor, patch = _read_version()
    if part == "major":
        major += 1
        minor = 0
        patch = 0
    elif part == "minor":
        minor += 1
        patch = 0
    else:
        patch += 1
    version = _write_version((major, minor, patch))
    today = _dt.date.today().isoformat()
    _insert_changelog_entry(version, message, date=today)
    _insert_release_note(version, message)
    return version


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    bump_parser = subparsers.add_parser("bump", help="Bump semantic version and update collateral")
    bump_parser.add_argument(
        "--part",
        choices=("major", "minor", "patch"),
        default="patch",
        help="Semantic version part to increment (default: patch).",
    )
    bump_parser.add_argument(
        "--message",
        default="TODO: describe release",
        help="Summary message recorded in CHANGELOG and RELEASE_NOTES.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "bump":
        version = bump_version(args.part, args.message)
        parser.exit(message=f"Bumped version to {version}\n")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
