"""Yahoo! Finance market data provider."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

import yfinance as yf

from apps.api.models.models import Price

__all__ = ["YFinanceProvider", "provider"]


class YFinanceProvider:
    """Fetch historical prices using the `yfinance` package."""

    name = "yfinance"

    def fetch_prices(self, symbol: str, start: date, end: date) -> Iterable[Price]:
        df = yf.download(
            symbol,
            start=start.isoformat(),
            end=end.isoformat(),
            progress=False,
            auto_adjust=False,
        )
        if df is None or df.empty:
            return []

        prices: list[Price] = []
        for idx, row in df.iterrows():
            prices.append(
                Price(
                    instrument_id=0,  # overwritten by MarketService
                    date=idx.date(),
                    close=float(row["Close"]),
                    provider=self.name,
                )
            )
        return prices


def provider() -> YFinanceProvider:
    """Entry point for the plugin loader."""

    return YFinanceProvider()
