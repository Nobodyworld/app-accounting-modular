"""Yahoo! Finance market data provider."""

from __future__ import annotations

import inspect
import logging
import math
import re
from collections.abc import Iterable
from datetime import date, datetime
from numbers import Real

import yfinance as yf  # type: ignore[import-untyped]
from apps.api.models.models import Price
from apps.provider_sdk import ProviderManifest

from plugins.provider_limits import (
    MAX_MARKET_PRICE_RECORDS,
    MAX_MARKET_REQUEST_DAYS,
    PROVIDER_READ_TIMEOUT_SECONDS,
    ProviderPayloadError,
    ProviderRequestError,
    ProviderResponseLimitError,
    ProviderTransportError,
)

__all__ = ["PROVIDER_MANIFEST", "YFinanceMarketProvider", "provider"]
__version__ = "0.3.0"

PROVIDER_MANIFEST = ProviderManifest(
    key="market:yfinance",
    name="Yahoo Finance Market Data",
    version=__version__,
    api_major=0,
    capabilities=("market",),
    description="Bounded high-level Yahoo Finance market-price adapter.",
    license="Apache-2.0",
    network_policy="https",
    data_classification="external-service",
)

logger = logging.getLogger(__name__)
_MARKET_SYMBOL = re.compile(r"^[A-Za-z0-9.^=_-]{1,32}$")
_YF_DOWNLOAD_PARAMETERS = frozenset(inspect.signature(yf.download).parameters)


class YFinanceMarketProvider:
    """Fetch prices through one bounded high-level ``yfinance`` call."""

    name = "yfinance"

    def fetch_prices(self, symbol: str, start: date, end: date) -> Iterable[Price]:
        if not isinstance(symbol, str) or not _MARKET_SYMBOL.fullmatch(symbol):
            raise ProviderRequestError("Provider request parameters are invalid")
        if not isinstance(start, date) or not isinstance(end, date) or start > end:
            raise ProviderRequestError("Provider request parameters are invalid")
        if (end - start).days > MAX_MARKET_REQUEST_DAYS:
            raise ProviderRequestError("Provider request parameters are invalid")

        download_options: dict[str, object] = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "progress": False,
            "auto_adjust": False,
            "threads": False,
        }
        if "timeout" in _YF_DOWNLOAD_PARAMETERS:
            download_options["timeout"] = PROVIDER_READ_TIMEOUT_SECONDS
        if "multi_level_index" in _YF_DOWNLOAD_PARAMETERS:
            download_options["multi_level_index"] = False
        try:
            df = yf.download(symbol, **download_options)
        except Exception as exc:
            logger.warning(
                "Outbound market provider request failed",
                extra={
                    "provider": self.name,
                    "operation": "fetch-prices",
                    "attempt": 1,
                    "failure_classification": "transport",
                },
            )
            raise ProviderTransportError("Provider request failed") from exc
        if df is None or df.empty:
            return []
        if len(df) > MAX_MARKET_PRICE_RECORDS:
            raise ProviderResponseLimitError("Provider response exceeded the configured limit")
        if "Close" not in df.columns:
            raise ProviderPayloadError("Provider returned an invalid payload")

        prices: list[Price] = []
        for idx, row in df.iterrows():
            try:
                if isinstance(idx, datetime):
                    idx_date = idx.date()
                elif isinstance(idx, date):
                    idx_date = idx
                else:
                    idx_date = date.fromisoformat(str(idx)[:10])
                raw_close = row["Close"]
                if isinstance(raw_close, bool):
                    raise ValueError
                if not isinstance(raw_close, Real):
                    raise ValueError
                close = float(raw_close)
                if not math.isfinite(close):
                    raise ValueError
            except (TypeError, ValueError) as exc:
                raise ProviderPayloadError("Provider returned an invalid payload") from exc
            prices.append(
                Price(
                    instrument_id=0,  # overwritten by MarketService
                    date=idx_date,
                    close=close,
                    provider=self.name,
                )
            )
        return prices


def provider() -> YFinanceMarketProvider:
    """Entry point for the plugin loader."""

    return YFinanceMarketProvider()
