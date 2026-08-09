from __future__ import annotations

from pathlib import Path

from tests.streamlit_helpers import REPOSITORY_ROOT, streamlit_app_path


def test_streamlit_app_path_is_absolute_and_independent_of_current_directory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    expected = (REPOSITORY_ROOT / "apps" / "web" / "app.py").resolve()

    monkeypatch.chdir(tmp_path)

    actual = Path(streamlit_app_path())
    assert actual.is_absolute()
    assert actual == expected
    assert actual.is_file()
