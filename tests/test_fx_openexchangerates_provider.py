import importlib
import itertools
import logging
import string
from datetime import date

import pytest
import requests
from plugins.fx_openexchangerates.provider import OpenExchangeRatesProvider
from plugins.provider_limits import (
    MAX_FX_RATE_RECORDS,
    ProviderPayloadError,
    ProviderResponseLimitError,
    ProviderTransportError,
)

provider_module = importlib.import_module("plugins.fx_openexchangerates.provider")
limits_module = importlib.import_module("plugins.provider_limits")


def _currency_rates(count: int) -> dict[str, float]:
    codes = ("".join(chars) for chars in itertools.product(string.ascii_uppercase, repeat=3))
    return {code: 1.0 for code in itertools.islice(codes, count)}


def test_provider_requires_app_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENEXCHANGERATES_APP_ID", raising=False)
    monkeypatch.setattr(provider_module.settings, "openex_app_id", None)
    with pytest.raises(ValueError):
        OpenExchangeRatesProvider()


def test_provider_syncs_rates(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_get(url: str, **kwargs: object) -> dict[str, object]:
        captured["url"] = url
        captured.update(kwargs)
        return {
            "base": "USD",
            "date": "2024-01-02",
            "rates": {"EUR": 0.9, "GBP": 0.8},
        }

    monkeypatch.setattr(provider_module, "get_bounded_json", fake_get)
    provider = OpenExchangeRatesProvider(app_id="dummy-key")
    rates = provider.sync_daily_rates(base="USD", date_=date(2024, 1, 2))

    assert captured["url"] == "https://openexchangerates.org/api/historical/2024-01-02.json"
    assert captured["params"] == {"app_id": "dummy-key", "base": "USD"}
    assert captured["provider_key"] == provider.name
    assert len(rates) == 2
    assert rates[0].provider == provider.name
    assert rates[0].date == date(2024, 1, 2)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"base": "USD", "date": "2024-01-02", "rates": {"EUR": 0.9}}, date(2024, 1, 2)),
        (
            {"base": "USD", "timestamp": 1704153600, "rates": {"EUR": 0.9}},
            date.fromtimestamp(1704153600),
        ),
        ({"base": "USD", "rates": {"EUR": 0.9}}, date(2024, 1, 3)),
    ],
)
def test_provider_preserves_date_and_timestamp_behavior(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, object],
    expected: date,
) -> None:
    monkeypatch.setattr(provider_module, "get_bounded_json", lambda url, **kwargs: payload)

    rates = OpenExchangeRatesProvider(app_id="dummy-key").sync_daily_rates(
        date_=date(2024, 1, 3),
    )
    assert rates[0].date == expected


def test_provider_accepts_exact_fx_record_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        provider_module,
        "get_bounded_json",
        lambda url, **kwargs: {"base": "USD", "rates": _currency_rates(MAX_FX_RATE_RECORDS)},
    )

    rates = OpenExchangeRatesProvider(app_id="dummy-key").sync_daily_rates()
    assert len(rates) == MAX_FX_RATE_RECORDS


def test_provider_rejects_fx_record_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        provider_module,
        "get_bounded_json",
        lambda url, **kwargs: {"base": "USD", "rates": _currency_rates(MAX_FX_RATE_RECORDS + 1)},
    )

    with pytest.raises(ProviderResponseLimitError):
        OpenExchangeRatesProvider(app_id="dummy-key").sync_daily_rates()


@pytest.mark.parametrize(
    "payload",
    [
        {"base": "USD", "rates": []},
        {"base": "USD", "rates": {"EURO": 1}},
        {"base": "USD", "rates": {"EUR": "private-upstream-value"}},
        {"base": "BAD!", "rates": {"EUR": 1}},
    ],
)
def test_provider_rejects_malformed_payload_safely(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, object],
) -> None:
    monkeypatch.setattr(provider_module, "get_bounded_json", lambda url, **kwargs: payload)

    with pytest.raises(ProviderPayloadError) as exc_info:
        OpenExchangeRatesProvider(app_id="dummy-key").sync_daily_rates()

    assert "private-upstream-value" not in str(exc_info.value)


def test_app_id_is_absent_from_errors_and_logs(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinel = "sentinel-app-id-must-not-escape"

    def failed_get(*args: object, **kwargs: object) -> requests.Response:
        raise requests.ConnectionError(f"https://upstream.invalid?app_id={sentinel}")

    monkeypatch.setattr(limits_module.requests, "get", failed_get)
    caplog.set_level(logging.WARNING)

    with pytest.raises(ProviderTransportError) as exc_info:
        OpenExchangeRatesProvider(app_id=sentinel).sync_daily_rates()

    assert sentinel not in str(exc_info.value)
    assert all(sentinel not in record.getMessage() for record in caplog.records)
    assert all(sentinel not in repr(record.__dict__) for record in caplog.records)
