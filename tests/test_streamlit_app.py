from __future__ import annotations

from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest


class DummyResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("request failed")


@pytest.fixture
def fake_requests(monkeypatch):
    from apps.web import app as streamlit_app

    budget_payload = {
        "lines": [
            {
                "account_id": 1,
                "account_code": "5000",
                "account_name": "Ops",
                "period_start": "2024-01-01",
                "budget_amount": 100.0,
                "actual_amount": 120.0,
                "variance": 20.0,
                "burn_rate": 1.2,
                "forecast": [["2024-02-01", 125.0]],
            }
        ],
        "summary": {
            "total_budget": 100.0,
            "total_actual": 120.0,
            "total_variance": 20.0,
            "burn_rate": 1.2,
        },
        "metadata": {
            "generated_at": "2024-02-01T00:00:00",
            "horizon": 30,
            "plan_id": 1,
            "budget_id": 1,
            "organization_id": 1,
        },
        "csv_export": "account_id,period_start,amount\n1,2024-01-01,120.0\n",
    }

    cashflow_payload = {
        "historical": [
            {"period": "2024-01-01", "amount": -100.0},
            {"period": "2024-02-01", "amount": -80.0},
        ],
        "forecast": [["2024-03-01", -90.0]],
        "model_order": (1, 0, 0),
        "metadata": {
            "generated_at": "2024-02-15T00:00:00",
            "horizon": 30,
            "plan_id": 2,
            "budget_id": None,
            "organization_id": 1,
        },
        "current_cash": -180.0,
        "average_monthly_flow": -90.0,
        "csv_export": "period,amount,type\n2024-01-01,-100.0,historical\n",
    }

    def fake_get(url: str, timeout: int = 5, params: dict | None = None):
        if url.endswith("/health"):
            return DummyResponse({"status": "ok"})
        if url.endswith("/providers"):
            return DummyResponse({"providers": []})
        if url.endswith("/reports/budget-vs-actual"):
            assert params["budget_id"] == 1
            return DummyResponse(budget_payload)
        if url.endswith("/reports/cashflow-forecast"):
            assert params["organization_id"] == 1
            return DummyResponse(cashflow_payload)
        return DummyResponse({"ok": True})

    def fake_post(url: str, params: dict | None = None, json: dict | None = None, timeout: int = 5):
        return DummyResponse({"ok": True})

    monkeypatch.setattr(streamlit_app, "requests", SimpleNamespace(get=fake_get, post=fake_post))
    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setenv("API_BASE", "http://fake")
    monkeypatch.setenv("STREAMLIT_TESTING", "1")
    return budget_payload, cashflow_payload


def test_budget_report_flow(fake_requests):
    at = AppTest.from_file("apps/web/app.py")
    at.run()

    at.number_input(key="budget_id_input").set_value(1)
    at.run()
    at.number_input(key="budget_horizon_input").set_value(45)
    at.run()
    at.checkbox(key="budget_refresh_toggle").check()
    at.run()
    at.button(key="budget_report_button").click()
    at.run()

    assert "budget_report_payload" in at.session_state
    summary = at.session_state["budget_report_payload"]["summary"]
    assert summary["total_actual"] == pytest.approx(120.0)


def test_budget_upload_preview(fake_requests):
    at = AppTest.from_file("apps/web/app.py")
    at.run()

    csv_bytes = b"account_id,period_start,amount\n1,2024-01-01,100\n"
    at.session_state["uploaded_budget_bytes"] = csv_bytes
    if "uploaded_budget_preview" in at.session_state:
        del at.session_state["uploaded_budget_preview"]
    at.run()

    assert "uploaded_budget_preview" in at.session_state
    preview = at.session_state["uploaded_budget_preview"]
    assert list(preview.columns) == ["account_id", "period_start", "amount"]


def test_cashflow_flow(fake_requests):
    at = AppTest.from_file("apps/web/app.py")
    at.run()

    at.number_input(key="cashflow_org_input").set_value(1)
    at.run()
    at.number_input(key="cashflow_horizon_input").set_value(30)
    at.run()
    at.checkbox(key="cashflow_refresh_toggle").check()
    at.run()
    at.button(key="cashflow_report_button").click()
    at.run()

    assert "cashflow_report_payload" in at.session_state
    payload = at.session_state["cashflow_report_payload"]
    assert payload["current_cash"] == pytest.approx(-180.0)
