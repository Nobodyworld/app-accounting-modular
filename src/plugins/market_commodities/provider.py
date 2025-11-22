"""Stub commodity and futures market data provider.

This provider returns deterministic synthetic prices for commodities or futures
symbols so downstream services can exercise market orchestration without
depending on external APIs. It implements the ``fetch_prices`` interface used
by :class:`MarketService`.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

from apps.api.models.models import Price


class CommodityFuturesProvider:
    """Return simple synthetic price curves for commodity/futures symbols."""

    name = "commodity_futures_stub"

    def __init__(self, *, base_price: float = 100.0, daily_drift: float = 0.25) -> None:
        self.base_price = base_price
        self.daily_drift = daily_drift

    def fetch_prices(self, symbol: str, start: date, end: date) -> Iterable[Price]:
        current = start
        idx = 0
        while current <= end:
            yield Price(
                instrument_id=None,
                date=current,
                close=round(self.base_price + idx * self.daily_drift, 4),
                provider=self.name,
            )
            current += timedelta(days=1)
            idx += 1


def provider() -> CommodityFuturesProvider:
    return CommodityFuturesProvider()
