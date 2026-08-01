from __future__ import annotations

import importlib
from datetime import date, timedelta

import pandas as pd
import pytest
from plugins.market_yfinance.provider import YFinanceMarketProvider
from plugins.provider_limits import (
    MAX_MARKET_PRICE_RECORDS,
    MAX_MARKET_REQUEST_DAYS,
    PROVIDER_READ_TIMEOUT_SECONDS,
    ProviderPayloadError,
    ProviderRequestError,
    ProviderResponseLimitError,
    ProviderTransportError,
)

provider_module = importlib.import_module("plugins.market_yfinance.provider")


def test_normal_dataframe_produces_expected_prices(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    frame = pd.DataFrame(
        {"Close": [101.5, 102.25]},
        index=pd.to_datetime(["2024-01-02", "2024-01-03"]),
    )

    def download(*args: object, **kwargs: object) -> pd.DataFrame:
        captured["args"] = args
        captured.update(kwargs)
        return frame

    monkeypatch.setattr(provider_module.yf, "download", download)
    prices = list(YFinanceMarketProvider().fetch_prices("ACME", date(2024, 1, 1), date(2024, 1, 4)))

    assert [price.close for price in prices] == [101.5, 102.25]
    assert [price.date for price in prices] == [date(2024, 1, 2), date(2024, 1, 3)]
    assert all(price.instrument_id == 0 for price in prices)
    assert captured["args"] == ("ACME",)
    assert captured["threads"] is False
    assert captured["timeout"] == PROVIDER_READ_TIMEOUT_SECONDS
    assert captured["progress"] is False
    assert captured["auto_adjust"] is False
    assert captured["multi_level_index"] is False


def test_empty_dataframe_returns_empty_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provider_module.yf, "download", lambda *args, **kwargs: pd.DataFrame())

    assert list(YFinanceMarketProvider().fetch_prices("ACME", date(2024, 1, 1), date(2024, 1, 2))) == []


def test_exact_market_record_limit_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    frame = pd.DataFrame(
        {"Close": [1.0] * MAX_MARKET_PRICE_RECORDS},
        index=pd.date_range("2000-01-01", periods=MAX_MARKET_PRICE_RECORDS),
    )
    monkeypatch.setattr(provider_module.yf, "download", lambda *args, **kwargs: frame)

    prices = list(YFinanceMarketProvider().fetch_prices("ACME", date(2024, 1, 1), date(2024, 1, 2)))
    assert len(prices) == MAX_MARKET_PRICE_RECORDS


def test_market_record_limit_is_rejected_before_iteration(monkeypatch: pytest.MonkeyPatch) -> None:
    class OversizedFrame:
        empty = False
        columns = ["Close"]

        def __len__(self) -> int:
            return MAX_MARKET_PRICE_RECORDS + 1

        def iterrows(self) -> object:
            pytest.fail("Oversized frame must be rejected before iteration")

    monkeypatch.setattr(provider_module.yf, "download", lambda *args, **kwargs: OversizedFrame())

    with pytest.raises(ProviderResponseLimitError):
        list(YFinanceMarketProvider().fetch_prices("ACME", date(2024, 1, 1), date(2024, 1, 2)))


def test_unreasonable_date_range_is_rejected_before_download(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def download(*args: object, **kwargs: object) -> pd.DataFrame:
        nonlocal calls
        calls += 1
        return pd.DataFrame()

    monkeypatch.setattr(provider_module.yf, "download", download)
    start = date(1990, 1, 1)

    with pytest.raises(ProviderRequestError):
        list(
            YFinanceMarketProvider().fetch_prices(
                "ACME",
                start,
                start + timedelta(days=MAX_MARKET_REQUEST_DAYS + 1),
            )
        )

    assert calls == 0


@pytest.mark.parametrize(
    "frame",
    [
        pd.DataFrame({"Open": [1.0]}, index=pd.to_datetime(["2024-01-02"])),
        pd.DataFrame({"Close": ["private-upstream-data"]}, index=pd.to_datetime(["2024-01-02"])),
        pd.DataFrame({"Close": [float("nan")]}, index=pd.to_datetime(["2024-01-02"])),
        pd.DataFrame({"Close": [1.0]}, index=["not-a-date"]),
    ],
)
def test_malformed_close_or_index_is_rejected_safely(
    monkeypatch: pytest.MonkeyPatch,
    frame: pd.DataFrame,
) -> None:
    monkeypatch.setattr(provider_module.yf, "download", lambda *args, **kwargs: frame)

    with pytest.raises(ProviderPayloadError) as exc_info:
        list(YFinanceMarketProvider().fetch_prices("ACME", date(2024, 1, 1), date(2024, 1, 3)))

    assert "private-upstream-data" not in str(exc_info.value)


def test_download_failure_is_sanitized_and_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def download(*args: object, **kwargs: object) -> pd.DataFrame:
        nonlocal calls
        calls += 1
        raise RuntimeError("private upstream response")

    monkeypatch.setattr(provider_module.yf, "download", download)

    with pytest.raises(ProviderTransportError, match="Provider request failed") as exc_info:
        list(YFinanceMarketProvider().fetch_prices("ACME", date(2024, 1, 1), date(2024, 1, 3)))

    assert calls == 1
    assert "private upstream response" not in str(exc_info.value)


@pytest.mark.parametrize("symbol", ["", " BAD", "BAD/QUERY", "A" * 33])
def test_invalid_symbol_is_rejected_before_download(
    monkeypatch: pytest.MonkeyPatch,
    symbol: str,
) -> None:
    calls = 0

    def download(*args: object, **kwargs: object) -> pd.DataFrame:
        nonlocal calls
        calls += 1
        return pd.DataFrame()

    monkeypatch.setattr(provider_module.yf, "download", download)

    with pytest.raises(ProviderRequestError):
        list(YFinanceMarketProvider().fetch_prices(symbol, date(2024, 1, 1), date(2024, 1, 2)))

    assert calls == 0
