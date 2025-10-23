"""Scheduler tests ensuring forecast refresh tasks handle failure isolation."""

from __future__ import annotations

from typing import Any

import pytest
from sqlmodel import Session, delete

from apps.api import scheduler
from apps.api.db import engine, init_db
from apps.api.models.models import ForecastPlan


class StubBudgetService:
    """Instrumented budget service capturing scheduler-triggered calls."""
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def budget_vs_actual(self, budget_id: int, *, horizon: int, refresh: bool) -> None:
        self.calls.append(
            (
                "budget",
                {
                    "budget_id": budget_id,
                    "horizon": horizon,
                    "refresh": refresh,
                },
            )
        )
        raise RuntimeError("boom")

    def cashflow_forecast(
        self, organization_id: int, *, horizon: int, refresh: bool
    ) -> None:
        self.calls.append(
            (
                "cashflow",
                {
                    "organization_id": organization_id,
                    "horizon": horizon,
                    "refresh": refresh,
                },
            )
        )


@pytest.fixture(autouse=True)
def clean_forecast_plans() -> None:
    init_db()
    with Session(engine) as session:
        session.exec(delete(ForecastPlan))
        session.commit()
    yield
    with Session(engine) as session:
        session.exec(delete(ForecastPlan))
        session.commit()


# TODO - (scheduler) Simulate distributed job runners once queue integration lands.


def test_run_scheduled_refresh_logs_failures_and_continues(monkeypatch, caplog) -> None:
    with Session(engine) as session:
        plan_with_budget = ForecastPlan(
            organization_id=1,
            budget_id=2,
            name="Budget Plan",
            horizon=45,
            is_active=True,
        )
        plan_cashflow = ForecastPlan(
            organization_id=5,
            budget_id=None,
            name="Cashflow Plan",
            horizon=30,
            is_active=True,
        )
        session.add(plan_with_budget)
        session.add(plan_cashflow)
        session.commit()
        session.refresh(plan_with_budget)
        session.refresh(plan_cashflow)

    stub = StubBudgetService()
    monkeypatch.setattr(scheduler, "BudgetService", lambda session: stub)

    with caplog.at_level("ERROR"):
        scheduler._run_scheduled_refresh()

    assert [call[0] for call in stub.calls] == ["budget", "cashflow"]
    assert stub.calls[0][1]["budget_id"] == 2
    assert stub.calls[1][1]["organization_id"] == 5

    error_logs = [record for record in caplog.records if record.levelname == "ERROR"]
    assert error_logs, "Expected an error log when the budget refresh fails"
    record = error_logs[0]
    assert record.message == "Failed to refresh forecast plan"
    assert record.plan_id == plan_with_budget.id
    assert record.organization_id == plan_with_budget.organization_id
    assert record.budget_id == plan_with_budget.budget_id
