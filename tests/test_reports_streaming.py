from __future__ import annotations

from apps.api.routers import reports
from apps.api.routers.reports import cashflow_forecast
from fastapi import Response


class _StubReport:
    def __init__(self) -> None:
        self.historical = []
        self.forecast = None
        self.metadata = {"generated_at": "2020-01-01T00:00:00Z"}
        self.current_cash = 0.0
        self.average_monthly_flow = 0.0
        self.csv_export = "a,b\n1,2"


class _StubService:
    def cashflow_forecast(self, organization_id: int, *, horizon: int | None, refresh: bool) -> _StubReport:
        return _StubReport()


def test_cashflow_forecast_streams_csv(monkeypatch):
    monkeypatch.setattr(reports, "BudgetService", lambda session: _StubService())
    response = cashflow_forecast(organization_id=1, session=None, stream_csv=True)  # type: ignore[arg-type]
    assert isinstance(response, Response)
    assert response.headers["content-type"].startswith("text/csv")
    assert response.body.decode() == "a,b\n1,2"
