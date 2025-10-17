"""Background scheduling utilities for periodic refresh tasks."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from apscheduler.schedulers.background import BackgroundScheduler
from sqlmodel import Session, select

from .db import engine
from .models.models import ForecastPlan
from .services.budget_service import BudgetService

__all__ = [
    "start_scheduler",
    "shutdown_scheduler",
]

_scheduler: BackgroundScheduler | None = None
logger = logging.getLogger(__name__)


@contextmanager
def _session_scope() -> Iterator[Session]:
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()


def _refresh_plan(service: BudgetService, plan: ForecastPlan) -> None:
    if plan.budget_id is not None:
        service.budget_vs_actual(plan.budget_id, horizon=plan.horizon, refresh=True)
    else:
        service.cashflow_forecast(
            plan.organization_id, horizon=plan.horizon, refresh=True
        )


def _run_scheduled_refresh() -> None:
    with _session_scope() as session:
        service = BudgetService(session)
        plans = session.exec(
            select(ForecastPlan).where(ForecastPlan.is_active.is_(True))
        ).all()
        for plan in plans:
            try:
                _refresh_plan(service, plan)
            except Exception:
                logger.exception(
                    "Failed to refresh forecast plan", extra={
                        "plan_id": plan.id,
                        "organization_id": plan.organization_id,
                        "budget_id": plan.budget_id,
                    }
                )


def start_scheduler() -> None:
    """Start the APScheduler if it is not already running."""

    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(daemon=True)
        _scheduler.add_job(
            _run_scheduled_refresh,
            "interval",
            hours=6,
            id="report-refresh",
            replace_existing=True,
        )
        _scheduler.start()


def shutdown_scheduler() -> None:
    """Stop the APScheduler if it is running."""

    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
