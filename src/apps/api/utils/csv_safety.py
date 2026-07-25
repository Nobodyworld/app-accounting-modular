"""Spreadsheet-safe formatting for generated CSV text cells."""

from __future__ import annotations

_FORMULA_PREFIXES = ("=", "+", "-", "@")


def safe_csv_text(value: object) -> str:
    """Return text that spreadsheet applications will not interpret as a formula.

    Generated numeric fields should remain numeric and must not be passed through
    this helper. Text cells beginning with a spreadsheet formula prefix receive
    a leading apostrophe, which common spreadsheet applications treat as an
    explicit text marker rather than executable spreadsheet syntax.
    """

    text = "" if value is None else str(value)
    if text.startswith(_FORMULA_PREFIXES):
        return f"'{text}"
    return text
