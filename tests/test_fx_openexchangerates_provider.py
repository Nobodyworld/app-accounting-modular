from datetime import date

import pytest

from plugins.fx_openexchangerates.provider import OpenExchangeRatesProvider


def test_provider_requires_app_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENEXCHANGERATES_APP_ID", raising=False)
    with pytest.raises(ValueError):
        OpenExchangeRatesProvider()


def test_provider_syncs_rates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENEXCHANGERATES_APP_ID", "dummy-key")
    captured: dict[str, object] = {}

    def fake_get(url, params=None, timeout=None):  # type: ignore[override]
        captured["url"] = url
        captured["params"] = params

        class Response:
            def raise_for_status(self) -> None:
                return None

            def json(self):
                return {
                    "base": "USD",
                    "date": "2024-01-02",
                    "rates": {"EUR": 0.9, "GBP": 0.8},
                }

        return Response()

    import importlib

    provider_module = importlib.import_module("plugins.fx_openexchangerates.provider")
    monkeypatch.setattr(provider_module.requests, "get", fake_get)
    provider = OpenExchangeRatesProvider()
    rates = provider.sync_daily_rates(base="USD", date_=date(2024, 1, 2))

    assert captured["url"] == "https://openexchangerates.org/api/historical/2024-01-02.json"
    assert captured["params"] == {"app_id": "dummy-key", "base": "USD"}
    assert len(rates) == 2
    assert rates[0].provider == provider.name
    assert rates[0].date == date(2024, 1, 2)
    assert {rate.quote for rate in rates} == {"EUR", "GBP"}
