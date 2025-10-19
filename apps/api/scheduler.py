"""Background scheduling utilities for periodic refresh tasks."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import timedelta
from threading import Lock
from typing import Iterator
from uuid import uuid4

from apscheduler.schedulers.background import BackgroundScheduler
from sqlmodel import Session, select

from apps.observability.logging import logging_context

from .db import engine
from .models.models import ForecastPlan
from .services.budget_service import BudgetService

__all__ = [
    "start_scheduler",
    "shutdown_scheduler",
]

_scheduler: BackgroundScheduler | None = None
_scheduler_lock = Lock()
_SCHEDULE_INTERVAL = timedelta(hours=6)
logger = logging.getLogger(__name__)


@contextmanager
def _session_scope() -> Iterator[Session]:
    session = Session(engine)
    # TODO - Implement retry/backoff for transient database connectivity issues.
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
    correlation = f"scheduler-{uuid4()}"
    with logging_context(
        correlation_id=correlation,
        request_id=correlation,
        job="forecast-refresh",
    ):
        logger.info("Running scheduled forecast refresh job")
        # TODO - Emit metrics or alerts when refresh frequency falls behind schedule.
        with _session_scope() as session:
            service = BudgetService(session)
            plans = session.exec(
                select(ForecastPlan).where(ForecastPlan.is_active.is_(True))
            ).all()
            if not plans:
                logger.info("No active forecast plans available for refresh")
                return
            for plan in plans:
                with logging_context(
                    plan_id=plan.id,
                    organization_id=plan.organization_id,
                    budget_id=plan.budget_id,
                ):
                    try:
                        _refresh_plan(service, plan)
                        logger.info("Refreshed forecast plan")
                    except Exception:
                        logger.exception("Failed to refresh forecast plan")


def start_scheduler() -> None:
    """Start the APScheduler if it is not already running."""

    global _scheduler
    with _scheduler_lock:
        if _scheduler is not None:
            if not _scheduler.running:
                logger.info("Starting scheduler that was instantiated but not running")
                _scheduler.start()
            return

        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(
            _run_scheduled_refresh,
            "interval",
            seconds=int(_SCHEDULE_INTERVAL.total_seconds()),
            id="report-refresh",
            replace_existing=True,
        )
        # TODO - Externalize refresh cadence into configuration per organization.
        try:
            scheduler.start()
        except Exception:  # pragma: no cover - protective guard
            logger.exception("Failed to start background scheduler")
            scheduler.shutdown(wait=False)
            raise

        _scheduler = scheduler
        logger.info("Background scheduler started", extra={"interval_seconds": _SCHEDULE_INTERVAL.total_seconds()})


def shutdown_scheduler() -> None:
    """Stop the APScheduler if it is running."""

    global _scheduler
    with _scheduler_lock:
        if _scheduler is not None:
            _scheduler.shutdown(wait=False)
            _scheduler = None
            logger.info("Background scheduler stopped")
