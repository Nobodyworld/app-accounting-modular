import importlib
from datetime import date

from plugins.fx_ecb.provider import ECBFXProvider

fx_ecb_provider = importlib.import_module("plugins.fx_ecb.provider")


class _DummyResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


def test_ecb_provider_uses_response_date_when_present(monkeypatch) -> None:
    provider = ECBFXProvider()

    def _fake_get(url: str, timeout: int):
        assert "latest?base=USD" in url
        assert timeout == 20
        return _DummyResponse(
            {
                "date": "2026-06-30",
                "rates": {"EUR": 0.92, "GBP": 0.78},
            }
        )

    monkeypatch.setattr(fx_ecb_provider.requests, "get", _fake_get)

    rates = provider.sync_daily_rates(base="USD")

    assert len(rates) == 2
    assert {rate.quote for rate in rates} == {"EUR", "GBP"}
    assert {rate.date for rate in rates} == {date(2026, 6, 30)}


def test_ecb_provider_uses_explicit_requested_date_when_payload_date_missing(monkeypatch) -> None:
    provider = ECBFXProvider()
    requested = date(2026, 5, 31)

    def _fake_get(url: str, timeout: int):
        assert requested.isoformat() in url
        assert timeout == 20
        return _DummyResponse({"rates": {"EUR": 0.93}})

    monkeypatch.setattr(fx_ecb_provider.requests, "get", _fake_get)

    rates = provider.sync_daily_rates(base="USD", date_=requested)

    assert len(rates) == 1
    assert rates[0].date == requested


def test_ecb_provider_uses_explicit_requested_date_when_payload_date_blank(monkeypatch) -> None:
    provider = ECBFXProvider()
    requested = date(2026, 5, 15)

    def _fake_get(url: str, timeout: int):
        assert requested.isoformat() in url
        assert timeout == 20
        return _DummyResponse({"date": "   ", "rates": {"EUR": 0.95}})

    monkeypatch.setattr(fx_ecb_provider.requests, "get", _fake_get)

    rates = provider.sync_daily_rates(base="USD", date_=requested)

    assert len(rates) == 1
    assert rates[0].date == requested


def test_ecb_provider_falls_back_to_today_when_no_payload_date_and_no_requested_date(monkeypatch) -> None:
    provider = ECBFXProvider()
    expected_today = date(2026, 7, 1)

    class _FakeDate:
        @staticmethod
        def fromisoformat(value: str) -> date:
            return date.fromisoformat(value)

        @staticmethod
        def today() -> date:
            return expected_today

    def _fake_get(url: str, timeout: int):
        assert "latest?base=USD" in url
        assert timeout == 20
        return _DummyResponse({"rates": {"EUR": 0.91}})

    monkeypatch.setattr(fx_ecb_provider.requests, "get", _fake_get)
    monkeypatch.setattr(fx_ecb_provider, "date", _FakeDate)

    rates = provider.sync_daily_rates(base="USD")

    assert len(rates) == 1
    assert rates[0].date == expected_today
