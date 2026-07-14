"""Scheduler tests ensuring forecast refresh tasks handle failure isolation."""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Lock
from typing import Any, cast

import pytest
from _pytest.logging import LogCaptureFixture
from apps.api import scheduler
from apps.api.models.models import ForecastPlan
from sqlalchemy import text
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, delete, select


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


class FakeScheduler:
    """Thread-safe APScheduler stand-in used for lifecycle assertions."""

    def __init__(self, *, start_error: Exception | None = None, shutdown_error: Exception | None = None) -> None:
        self.running = False
        self.start_error = start_error
        self.shutdown_error = shutdown_error
        self.start_calls = 0
        self.shutdown_calls = 0
        self.add_job_calls = 0
        self._lock = Lock()

    def add_job(self, *args: object, **kwargs: object) -> None:
        with self._lock:
            self.add_job_calls += 1

    def start(self) -> None:
        with self._lock:
            self.start_calls += 1
            if self.start_error is not None:
                raise self.start_error
            self.running = True

    def shutdown(self, *, wait: bool) -> None:
        with self._lock:
            self.shutdown_calls += 1
            if self.shutdown_error is not None:
                raise self.shutdown_error
            self.running = False

    def get_jobs(self) -> list[object]:
        return []


@pytest.fixture(autouse=True)
def clean_forecast_plans(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(scheduler, "engine", engine)
    monkeypatch.setattr(scheduler, "_scheduler", None)
    monkeypatch.setattr(scheduler, "_last_run_at", None)

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
    monkeypatch.setattr(scheduler, "_scheduler", None)
    monkeypatch.setattr(scheduler, "_last_run_at", None)
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
        budget_plan_id = plan_with_budget.id
        cashflow_plan_id = plan_cashflow.id

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
    assert record.__dict__.get("plan_id") == budget_plan_id
    assert record.__dict__.get("organization_id") == plan_with_budget.organization_id
    assert record.__dict__.get("budget_id") == plan_with_budget.budget_id

    with Session(scheduler_engine) as session:
        failed_plan = session.get(ForecastPlan, budget_plan_id)
        successful_plan = session.get(ForecastPlan, cashflow_plan_id)
        assert failed_plan is not None
        assert successful_plan is not None
        assert failed_plan.last_refreshed_at is None
        assert successful_plan.last_refreshed_at is not None


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
    monkeypatch.setattr(scheduler, "sleep", lambda seconds: None)

    with pytest.raises(RuntimeError):
        with scheduler._session_scope():
            pass
    assert len(calls) == len(scheduler._RETRY_DELAY_SECONDS) + 1


def test_scheduler_session_scope_rolls_back_and_closes_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.rollback_calls = 0
            self.close_calls = 0

        def rollback(self) -> None:
            self.rollback_calls += 1

        def close(self) -> None:
            self.close_calls += 1

    fake = FakeSession()
    monkeypatch.setattr(scheduler, "Session", lambda bind: fake)

    with pytest.raises(RuntimeError, match="job failed"):
        with scheduler._session_scope():
            raise RuntimeError("job failed")

    assert fake.rollback_calls == 1
    assert fake.close_calls == 1


def test_scheduler_session_scope_closes_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.rollback_calls = 0
            self.close_calls = 0

        def rollback(self) -> None:
            self.rollback_calls += 1

        def close(self) -> None:
            self.close_calls += 1

    fake = FakeSession()
    monkeypatch.setattr(scheduler, "Session", lambda bind: fake)

    with scheduler._session_scope() as opened:
        assert opened is fake

    assert fake.rollback_calls == 0
    assert fake.close_calls == 1


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


def test_scheduler_handles_naive_refresh_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    scheduler_engine = cast(Any, scheduler.engine)
    with Session(scheduler_engine) as session:
        session.add(
            ForecastPlan(
                organization_id=1,
                budget_id=None,
                name="Naive Timestamp",
                horizon=10,
                is_active=True,
                refresh_interval_minutes=9999,
                last_refreshed_at=datetime.now().replace(microsecond=0),
            )
        )
        session.commit()

    stub = StubBudgetService()
    monkeypatch.setattr(scheduler, "BudgetService", lambda session: stub)
    scheduler._run_scheduled_refresh()
    assert not stub.calls


def test_scheduler_logs_no_active_plans(caplog: LogCaptureFixture) -> None:
    with caplog.at_level("INFO"):
        scheduler._run_scheduled_refresh()
    assert any(record.message == "No active forecast plans available for refresh" for record in caplog.records)


def test_start_and_shutdown_are_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeScheduler()
    monkeypatch.setattr(scheduler, "BackgroundScheduler", lambda daemon: fake)

    scheduler.start_scheduler()
    scheduler.start_scheduler()
    assert fake.add_job_calls == 1
    assert fake.start_calls == 1
    assert scheduler.get_scheduler_state()["running"] is True

    scheduler.shutdown_scheduler()
    scheduler.shutdown_scheduler()
    assert fake.shutdown_calls == 1
    assert scheduler.get_scheduler_state() == {"running": False, "jobs": 0, "next_run": None}
    assert scheduler._last_run_at is None


def test_startup_failure_cleanup_does_not_mask_original_error(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeScheduler(
        start_error=RuntimeError("start failed"),
        shutdown_error=RuntimeError("cleanup failed"),
    )
    monkeypatch.setattr(scheduler, "BackgroundScheduler", lambda daemon: fake)

    with pytest.raises(RuntimeError, match="start failed"):
        scheduler.start_scheduler()

    assert fake.start_calls == 1
    assert fake.shutdown_calls == 1
    assert scheduler._scheduler is None


def test_restart_failure_clears_stale_scheduler(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeScheduler(start_error=RuntimeError("restart failed"))
    monkeypatch.setattr(scheduler, "_scheduler", fake)

    with pytest.raises(RuntimeError, match="restart failed"):
        scheduler.start_scheduler()

    assert fake.start_calls == 1
    assert fake.shutdown_calls == 1
    assert scheduler._scheduler is None


def test_concurrent_lifecycle_calls_start_and_stop_once(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeScheduler()
    factory_calls: list[int] = []

    def factory(daemon: bool) -> FakeScheduler:
        factory_calls.append(1)
        return fake

    monkeypatch.setattr(scheduler, "BackgroundScheduler", factory)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: scheduler.start_scheduler(), range(16)))

    assert len(factory_calls) == 1
    assert fake.add_job_calls == 1
    assert fake.start_calls == 1

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: scheduler.shutdown_scheduler(), range(16)))

    assert fake.shutdown_calls == 1
    assert scheduler._scheduler is None
