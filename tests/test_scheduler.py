"""Scheduler tests ensuring forecast refresh tasks handle failure isolation."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from _pytest.logging import LogCaptureFixture
from apps.api import scheduler
from apps.api.models.models import ForecastPlan
from sqlalchemy import text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, delete


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

    def cashflow_forecast(self, organization_id: int, *, horizon: int, refresh: bool) -> None:
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
def clean_forecast_plans(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(scheduler, "engine", engine)

    with Session(engine) as session:
        # Ensure new columns exist for refreshed schema
        columns = {row[1] for row in session.exec(cast(Any, text("PRAGMA table_info('forecastplan')")))}
        if "refresh_interval_minutes" not in columns:
            session.exec(
                cast(Any, text("ALTER TABLE forecastplan ADD COLUMN refresh_interval_minutes INTEGER DEFAULT 360"))
            )
        if "last_refreshed_at" not in columns:
            session.exec(cast(Any, text("ALTER TABLE forecastplan ADD COLUMN last_refreshed_at TIMESTAMP")))
        session.exec(delete(ForecastPlan))
        session.commit()
    yield
    with Session(engine) as session:
        session.exec(delete(ForecastPlan))
        session.commit()
    engine.dispose()


# TODO - (scheduler) Simulate distributed job runners once queue integration lands.


def test_run_scheduled_refresh_logs_failures_and_continues(
    monkeypatch: pytest.MonkeyPatch, caplog: LogCaptureFixture
) -> None:
    scheduler_engine = cast(Any, scheduler.engine)
    with Session(scheduler_engine) as session:
        plan_with_budget = ForecastPlan(
            organization_id=1,
            budget_id=2,
            name="Budget Plan",
            horizon=45,
            is_active=True,
            refresh_interval_minutes=0,
        )
        plan_cashflow = ForecastPlan(
            organization_id=5,
            budget_id=None,
            name="Cashflow Plan",
            horizon=30,
            is_active=True,
            refresh_interval_minutes=0,
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
    assert record.__dict__.get("plan_id") == plan_with_budget.id
    assert record.__dict__.get("organization_id") == plan_with_budget.organization_id
    assert record.__dict__.get("budget_id") == plan_with_budget.budget_id


def test_scheduler_session_scope_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class FailingEngine:
        def __init__(self) -> None:
            self.attempts = 0

    def failing_session(bind: object = None, **_: object) -> Session:
        calls.append("attempt")
        raise RuntimeError("transient")

    engine_stub = FailingEngine()
    monkeypatch.setattr(scheduler, "engine", engine_stub)
    monkeypatch.setattr(scheduler, "Session", failing_session)

    with pytest.raises(RuntimeError):
        with scheduler._session_scope():
            pass
    assert len(calls) == len(scheduler._RETRY_DELAY_SECONDS) + 1


def test_scheduler_warns_when_behind_schedule(caplog: LogCaptureFixture) -> None:
    scheduler._last_run_at = datetime.now(UTC) - scheduler._SCHEDULE_INTERVAL * 2
    with caplog.at_level("WARNING"):
        scheduler._run_scheduled_refresh()
    warnings = [record for record in caplog.records if "cadence behind" in record.message]
    assert warnings
    assert cast(int, warnings[0].__dict__.get("delay_seconds", 0)) > 0


def test_scheduler_skips_plans_not_due(monkeypatch: pytest.MonkeyPatch) -> None:
    scheduler_engine = cast(Any, scheduler.engine)
    with Session(scheduler_engine) as session:
        plan = ForecastPlan(
            organization_id=1,
            budget_id=None,
            name="Not Due",
            horizon=10,
            is_active=True,
            refresh_interval_minutes=9999,
            last_refreshed_at=datetime.now(UTC),
        )
        session.add(plan)
        session.commit()
        session.refresh(plan)

    stub = StubBudgetService()
    monkeypatch.setattr(scheduler, "BudgetService", lambda session: stub)
    scheduler._run_scheduled_refresh()
    assert not stub.calls
