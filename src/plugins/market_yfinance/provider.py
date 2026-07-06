"""Yahoo! Finance market data provider."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime

import yfinance as yf  # type: ignore[import-untyped]
from apps.api.models.models import Price

__all__ = ["YFinanceMarketProvider", "provider"]


class YFinanceMarketProvider:
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
            if isinstance(idx, datetime):
                idx_date = idx.date()
            elif isinstance(idx, date):
                idx_date = idx
            else:
                idx_date = date.fromisoformat(str(idx)[:10])
            prices.append(
                Price(
                    instrument_id=0,  # overwritten by MarketService
                    date=idx_date,
                    close=float(row["Close"]),
                    provider=self.name,
                )
            )
        return prices


def provider() -> YFinanceMarketProvider:
    """Entry point for the plugin loader."""

    return YFinanceMarketProvider()
