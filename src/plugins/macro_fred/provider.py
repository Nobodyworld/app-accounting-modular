"""Stub provider for macroeconomic time series sourced from FRED-style feeds."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta


class FREDMacroProvider:
    """Return synthetic macroeconomic series for testing."""

    name = "fred_macro_stub"

    def fetch_series(self, series_id: str, start: date, end: date) -> Iterable[tuple[date, float]]:
        """Return a simple trend series for the given macro indicator."""

        current = start
        idx = 0
        while current <= end:
            value = 100.0 + idx * 0.5 if series_id.lower() == "gdp" else 50.0 + idx * 0.2
            yield current, value
            current += timedelta(days=30)
            idx += 1


def provider() -> FREDMacroProvider:
    return FREDMacroProvider()
