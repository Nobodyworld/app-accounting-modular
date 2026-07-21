"""Regression coverage for side-effect-free web package imports."""

from __future__ import annotations

import importlib
import sys


def test_importing_web_package_does_not_execute_streamlit_app() -> None:
    """Importing ``apps.web`` must not import or run the Streamlit page."""

    sys.modules.pop("apps.web.app", None)
    sys.modules.pop("apps.web", None)

    package = importlib.import_module("apps.web")

    assert package.__all__ == []
    assert "apps.web.app" not in sys.modules
