from __future__ import annotations

from datetime import UTC, date, datetime

from apps.api.models.models import Budget
from apps.api.routers import reports
from apps.api.routers.reports import budget_vs_actual
from apps.api.services.budget_service import BudgetReport, BudgetVarianceLine


class _StubService:
    def budget_vs_actual(self, budget_id: int, *, horizon: int | None, refresh: bool) -> BudgetReport:
        lines = [
            BudgetVarianceLine(
                account_id=i,
                account_code=f"C{i}",
                account_name=f"Account {i}",
                period_start=date(2024, 1, i + 1),
                budget_amount=10.0,
                actual_amount=5.0,
                variance=-5.0,
                burn_rate=0.5,
                forecast=None,
            )
            for i in range(3)
        ]
        return BudgetReport(
            lines=lines,
            total_budget=30.0,
            total_actual=15.0,
            total_variance=-15.0,
            burn_rate=0.5,
            metadata={"generated_at": datetime.now(UTC)},
            csv_export="",
        )


def test_budget_vs_actual_pagination(monkeypatch):
    monkeypatch.setattr(reports, "BudgetService", lambda session: _StubService())
    fake_budget = Budget(
        id=1, organization_id=1, name="stub", start_date=date(2024, 1, 1), end_date=date(2024, 12, 31), currency="USD"
    )  # type: ignore[call-arg]
    session = type("S", (), {"get": lambda self, model, id: fake_budget})()  # type: ignore[type-arg]
    resp = budget_vs_actual(budget_id=1, organization_id=1, limit=1, offset=1, session=session)  # type: ignore[arg-type]
    assert len(resp.lines) == 1
    assert resp.lines[0].account_id == 1
    assert resp.metadata.total_lines == 3
    assert resp.metadata.limit == 1
    assert resp.metadata.offset == 1
