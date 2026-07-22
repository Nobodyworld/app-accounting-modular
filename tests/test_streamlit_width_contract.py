from pathlib import Path


APP_FILE = Path("src/apps/web/app.py")


def test_streamlit_app_uses_supported_width_arguments() -> None:
    source = APP_FILE.read_text(encoding="utf-8")

    assert "use_container_width=" not in source
    assert 'width="stretch"' in source
