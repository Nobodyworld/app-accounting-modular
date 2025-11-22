from __future__ import annotations

from datetime import UTC, datetime

from apps.api.routers import reports
from apps.api.routers.reports import cashflow_forecast


class _StubReport:
    def __init__(self, marker: str) -> None:
        self.historical = []
        self.forecast = None
        self.metadata = {"marker": marker, "generated_at": datetime.now(UTC).isoformat()}
        self.current_cash = 0.0
        self.average_monthly_flow = 0.0
        self.csv_export = ""


class _StubService:
    def __init__(self) -> None:
        self.calls = 0

    def cashflow_forecast(self, organization_id: int, *, horizon: int | None, refresh: bool) -> _StubReport:
        self.calls += 1
        return _StubReport(marker=f"{organization_id}:{horizon}:{self.calls}")


def test_cashflow_forecast_uses_cache(monkeypatch):
    stub = _StubService()
    monkeypatch.setattr(reports, "BudgetService", lambda session: stub)
    reports._cashflow_cache.clear()

    first = cashflow_forecast(organization_id=1, session=None)  # type: ignore[arg-type]
    second = cashflow_forecast(organization_id=1, session=None)  # type: ignore[arg-type]

    assert stub.calls == 1
    assert first.metadata.model_dump()["marker"] == "1:None:1"  # type: ignore[union-attr]
    assert second.metadata.model_dump()["marker"] == "1:None:1"  # type: ignore[union-attr]
