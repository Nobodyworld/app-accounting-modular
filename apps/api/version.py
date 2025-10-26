"""Centralised version discovery for the Modular Accounting API."""

from __future__ import annotations

from pathlib import Path

__all__ = ["API_VERSION"]

_VERSION_FILE = Path(__file__).resolve().parents[2] / "VERSION"

try:
    API_VERSION = _VERSION_FILE.read_text(encoding="utf-8").strip()
except OSError:  # pragma: no cover - fallback when version file missing
    API_VERSION = "0.0.0"
