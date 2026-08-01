import importlib
import itertools
import string
from datetime import date

import pytest
from plugins.fx_ecb.provider import ECBFXProvider
from plugins.provider_limits import (
    MAX_FX_RATE_RECORDS,
    ProviderPayloadError,
    ProviderResponseLimitError,
)

fx_ecb_provider = importlib.import_module("plugins.fx_ecb.provider")


def _currency_rates(count: int) -> dict[str, float]:
    codes = ("".join(chars) for chars in itertools.product(string.ascii_uppercase, repeat=3))
    return {code: 1.0 for code in itertools.islice(codes, count)}


def test_ecb_provider_uses_response_date_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = ECBFXProvider()
    captured: dict[str, object] = {}

    def _fake_get(url: str, **kwargs: object) -> dict[str, object]:
        captured["url"] = url
        captured.update(kwargs)
        return {
            "date": "2026-06-30",
            "rates": {"EUR": 0.92, "GBP": 0.78},
        }

    monkeypatch.setattr(fx_ecb_provider, "get_bounded_json", _fake_get)
    rates = provider.sync_daily_rates(base="USD")

    assert captured["url"] == "https://api.exchangerate.host/latest"
    assert captured["params"] == {"base": "USD"}
    assert captured["provider_key"] == provider.name
    assert len(rates) == 2
    assert {rate.quote for rate in rates} == {"EUR", "GBP"}
    assert {rate.date for rate in rates} == {date(2026, 6, 30)}


def test_ecb_provider_uses_explicit_requested_date_when_payload_date_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = ECBFXProvider()
    requested = date(2026, 5, 31)

    monkeypatch.setattr(
        fx_ecb_provider,
        "get_bounded_json",
        lambda url, **kwargs: {"rates": {"EUR": 0.93}},
    )

    rates = provider.sync_daily_rates(base="USD", date_=requested)
    assert len(rates) == 1
    assert rates[0].date == requested


def test_ecb_provider_uses_explicit_requested_date_when_payload_date_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = ECBFXProvider()
    requested = date(2026, 5, 15)
    monkeypatch.setattr(
        fx_ecb_provider,
        "get_bounded_json",
        lambda url, **kwargs: {"date": "   ", "rates": {"EUR": 0.95}},
    )

    rates = provider.sync_daily_rates(base="USD", date_=requested)
    assert len(rates) == 1
    assert rates[0].date == requested


def test_ecb_provider_falls_back_to_today_when_no_dates(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = ECBFXProvider()
    expected_today = date(2026, 7, 1)

    class _FakeDate:
        @staticmethod
        def fromisoformat(value: str) -> date:
            return date.fromisoformat(value)

        @staticmethod
        def today() -> date:
            return expected_today

    monkeypatch.setattr(
        fx_ecb_provider,
        "get_bounded_json",
        lambda url, **kwargs: {"rates": {"EUR": 0.91}},
    )
    monkeypatch.setattr(fx_ecb_provider, "date", _FakeDate)

    rates = provider.sync_daily_rates(base="USD")
    assert rates[0].date == expected_today


def test_ecb_accepts_exact_fx_record_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fx_ecb_provider,
        "get_bounded_json",
        lambda url, **kwargs: {"rates": _currency_rates(MAX_FX_RATE_RECORDS)},
    )

    assert len(ECBFXProvider().sync_daily_rates()) == MAX_FX_RATE_RECORDS


def test_ecb_rejects_record_limit_before_model_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fx_ecb_provider,
        "get_bounded_json",
        lambda url, **kwargs: {"rates": _currency_rates(MAX_FX_RATE_RECORDS + 1)},
    )
    monkeypatch.setattr(
        fx_ecb_provider,
        "Rate",
        lambda **kwargs: pytest.fail("Rate construction must not start for oversized payloads"),
    )

    with pytest.raises(ProviderResponseLimitError):
        ECBFXProvider().sync_daily_rates()


@pytest.mark.parametrize(
    "payload",
    [
        {"rates": []},
        {"rates": {"EURO": 1}},
        {"rates": {"EUR": "not-a-rate"}},
        {"rates": {"EUR": float("nan")}},
        {"rates": {"EUR": True}},
    ],
)
def test_ecb_rejects_malformed_rates_safely(monkeypatch: pytest.MonkeyPatch, payload: object) -> None:
    monkeypatch.setattr(fx_ecb_provider, "get_bounded_json", lambda url, **kwargs: payload)

    with pytest.raises(ProviderPayloadError, match="invalid payload") as exc_info:
        ECBFXProvider().sync_daily_rates()

    assert "not-a-rate" not in str(exc_info.value)
