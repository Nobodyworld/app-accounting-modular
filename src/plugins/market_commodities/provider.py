"""Stub commodity and futures market data provider.

This provider returns deterministic synthetic prices for commodities or futures
symbols so downstream services can exercise market orchestration without
depending on external APIs. It implements the ``fetch_prices`` interface used
by :class:`MarketService`.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta

from apps.api.models.models import Price
from apps.provider_sdk import ProviderManifest

__version__ = "0.3.0"

PROVIDER_MANIFEST = ProviderManifest(
    key="market:commodities_demo",
    name="Synthetic Commodity & Futures Demo",
    version=__version__,
    api_major=0,
    capabilities=("market",),
    description="Deterministic commodity and futures price sample adapter.",
    license="Apache-2.0",
    network_policy="none",
    data_classification="controlled-sample",
)


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
                instrument_id=0,  # overwritten by MarketService before persistence
                date=current,
                close=round(self.base_price + idx * self.daily_drift, 4),
                provider=self.name,
            )
            current += timedelta(days=1)
            idx += 1


def provider() -> CommodityFuturesProvider:
    return CommodityFuturesProvider()
