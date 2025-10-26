from pathlib import Path

from tools import release_manager


def test_bump_version_updates_artifacts(tmp_path: Path, monkeypatch) -> None:
    version_file = tmp_path / "VERSION"
    changelog_file = tmp_path / "CHANGELOG.md"
    release_notes_file = tmp_path / "RELEASE_NOTES.md"

    version_file.write_text("1.2.3\n", encoding="utf-8")
    changelog_file.write_text("# Changelog\n## Unreleased\n\n", encoding="utf-8")
    release_notes_file.write_text("# Release Notes\n## Highlights\n", encoding="utf-8")

    monkeypatch.setattr(release_manager, "VERSION_FILE", version_file)
    monkeypatch.setattr(release_manager, "CHANGELOG_FILE", changelog_file)
    monkeypatch.setattr(release_manager, "RELEASE_NOTES_FILE", release_notes_file)

    version = release_manager.bump_version("minor", "Refreshed release tooling")

    assert version == "1.3.0"
    changelog = changelog_file.read_text(encoding="utf-8")
    release_notes = release_notes_file.read_text(encoding="utf-8")
    assert "v1.3.0" in changelog
    assert "Refreshed release tooling" in changelog
    assert "v1.3.0" in release_notes
