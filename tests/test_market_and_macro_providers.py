from datetime import date

from plugins.macro_fred.provider import FREDMacroProvider
from plugins.market_commodities.provider import CommodityFuturesProvider


def test_commodity_provider_generates_prices() -> None:
    provider = CommodityFuturesProvider(base_price=50.0, daily_drift=1.0)
    prices = list(provider.fetch_prices("XAU", date(2024, 1, 1), date(2024, 1, 3)))
    assert len(prices) == 3
    assert prices[0].close == 50.0
    assert prices[-1].close == 52.0
    assert all(price.provider == provider.name for price in prices)


def test_macro_provider_returns_series() -> None:
    provider = FREDMacroProvider()
    series = list(provider.fetch_series("GDP", date(2024, 1, 1), date(2024, 3, 1)))
    assert series
    timestamps = [ts for ts, _ in series]
    assert timestamps[0] == date(2024, 1, 1)
    assert all(value >= 100 for _, value in series)
