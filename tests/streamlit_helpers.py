"""Shared helpers for Streamlit application tests."""

from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
STREAMLIT_COMPATIBILITY_LAUNCHER = (REPOSITORY_ROOT / "apps" / "web" / "app.py").resolve()


def streamlit_app_path() -> str:
    """Return the absolute compatibility-launcher path, independent of the current directory."""

    if not STREAMLIT_COMPATIBILITY_LAUNCHER.is_file():
        raise FileNotFoundError(f"Streamlit compatibility launcher is missing: {STREAMLIT_COMPATIBILITY_LAUNCHER}")
    return str(STREAMLIT_COMPATIBILITY_LAUNCHER)
