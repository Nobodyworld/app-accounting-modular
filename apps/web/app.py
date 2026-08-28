"""Shim to execute the Streamlit app located under src/apps/web/app.py for tests."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
SDK_ROOT = Path(__file__).resolve().parents[2] / "packages" / "provider-sdk" / "src"
for source_root in (SDK_ROOT, SRC_ROOT):
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))

runpy.run_path(str(SRC_ROOT / "apps" / "web" / "app.py"), run_name="__main__")
