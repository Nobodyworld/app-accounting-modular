"""Background scheduler for regenerating forecast reports."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from apscheduler.schedulers.background import BackgroundScheduler
from sqlmodel import Session, select

from .db import engine
from .models.models import ForecastPlan
from .services.budget_service import BudgetService

_scheduler: BackgroundScheduler | None = None


@contextmanager
def _session_scope() -> Iterator[Session]:
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()


def _run_scheduled_refresh() -> None:
    with _session_scope() as session:
        service = BudgetService(session)
        plans = session.exec(select(ForecastPlan).where(ForecastPlan.is_active == True)).all()  # noqa: E712
        for plan in plans:
            if plan.budget_id is not None:
                try:
                    service.budget_vs_actual(plan.budget_id, horizon=plan.horizon, refresh=True)
                except Exception:
                    continue
            else:
                try:
                    service.cashflow_forecast(plan.organization_id, horizon=plan.horizon, refresh=True)
                except Exception:
                    continue


def start_scheduler() -> None:
    """Start the APScheduler if it is not already running."""

    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(daemon=True)
        _scheduler.add_job(_run_scheduled_refresh, "interval", hours=6, id="report-refresh", replace_existing=True)
        _scheduler.start()


def shutdown_scheduler() -> None:
    """Stop the APScheduler if it is running."""

    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
