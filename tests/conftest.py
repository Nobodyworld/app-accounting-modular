"""Pytest configuration utilities and compatibility shims for test suite."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ensure_multipart_dependency() -> None:
    """Ensure python-multipart is importable; fall back to stub when absent."""

    try:
        import python_multipart  # noqa: F401

        return
    except ImportError:
        try:
            import importlib

            importlib.import_module("python_multipart")  # type: ignore[unused-ignore]
        except Exception:
            import types

            stub = types.ModuleType("multipart")
            stub.__version__ = "0.0"

            multipart_mod = types.ModuleType("multipart.multipart")

            def parse_options_header(value: str | bytes) -> tuple[str, dict[str, str]]:
                if isinstance(value, bytes):
                    value = value.decode("latin-1")
                if not isinstance(value, str):
                    raise TypeError("Header value must be str or bytes")
                parts = [part.strip() for part in value.split(";") if part.strip()]
                if not parts:
                    return "", {}
                media_type = parts[0].lower()
                params: dict[str, str] = {}
                for item in parts[1:]:
                    if "=" in item:
                        key, _, raw_val = item.partition("=")
                        params[key.lower()] = raw_val.strip("\"'")
                return media_type, params

            multipart_mod.parse_options_header = parse_options_header
            stub.multipart = multipart_mod  # type: ignore[attr-defined]
            sys.modules["multipart"] = stub
            sys.modules["multipart.multipart"] = multipart_mod


_ensure_multipart_dependency()


# TODO - (tests) Replace stub when official lightweight multipart dependency is chosen.
