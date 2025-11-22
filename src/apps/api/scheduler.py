"""Background scheduling utilities for periodic refresh tasks."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from time import sleep
from threading import Lock
from uuid import uuid4

from apscheduler.schedulers.background import BackgroundScheduler
from sqlmodel import Session, select

from apps.observability.logging import logging_context

from .db import engine
from .services.budget_service import BudgetService

from .models.models import ForecastPlan

__all__ = [
    "start_scheduler",
    "shutdown_scheduler",
    "get_scheduler_state",
]

_scheduler: BackgroundScheduler | None = None
_scheduler_lock = Lock()
_SCHEDULE_INTERVAL = timedelta(minutes=15)
_RETRY_DELAY_SECONDS = (1, 2, 4)
_last_run_at: datetime | None = None
logger = logging.getLogger(__name__)


@contextmanager
def _session_scope() -> Iterator[Session]:
    attempt = 0
    while True:
        try:
            session = Session(engine)
            break
        except Exception:
            if attempt >= len(_RETRY_DELAY_SECONDS):
                raise
            delay = _RETRY_DELAY_SECONDS[attempt]
            attempt += 1
            logger.warning("Failed to create DB session; retrying", extra={"attempt": attempt, "delay": delay})
            sleep(delay)

    try:
        yield session
    finally:
        session.close()


def _refresh_plan(service: BudgetService, plan: ForecastPlan) -> None:
    if plan.budget_id is not None:
        service.budget_vs_actual(plan.budget_id, horizon=plan.horizon, refresh=True)
    else:
        service.cashflow_forecast(plan.organization_id, horizon=plan.horizon, refresh=True)
    plan.last_refreshed_at = datetime.now(UTC)


def _run_scheduled_refresh() -> None:
    correlation = f"scheduler-{uuid4()}"
    global _last_run_at
    now = datetime.now(UTC)
    if _last_run_at is not None:
        delay = (now - _last_run_at) - _SCHEDULE_INTERVAL
        if delay.total_seconds() > 0:
            logger.warning(
                "Scheduler refresh cadence behind schedule",
                extra={
                    "delay_seconds": int(delay.total_seconds()),
                    "last_run_at": _last_run_at.isoformat(),
                    "expected_interval_seconds": int(_SCHEDULE_INTERVAL.total_seconds()),
                },
            )
    _last_run_at = now
    with logging_context(
        correlation_id=correlation,
        request_id=correlation,
        job="forecast-refresh",
    ):
        logger.info("Running scheduled forecast refresh job")
        # TODO[P2][2d]: Emit metrics or alerts when refresh cadence falls behind schedule.
        with _session_scope() as session:
            service = BudgetService(session)
            plans = session.exec(select(ForecastPlan).where(ForecastPlan.is_active == True)).all()  # noqa: E712
            if not plans:
                logger.info("No active forecast plans available for refresh")
                return
            for plan in plans:
                interval = timedelta(minutes=plan.refresh_interval_minutes or int(_SCHEDULE_INTERVAL.total_seconds() / 60))
                if plan.last_refreshed_at is not None:
                    refreshed = plan.last_refreshed_at
                    if refreshed.tzinfo is None:
                        refreshed = refreshed.replace(tzinfo=UTC)
                    if (now - refreshed) < interval:
                        continue
                with logging_context(
                    plan_id=plan.id,
                    organization_id=plan.organization_id,
                    budget_id=plan.budget_id,
                ):
                    try:
                        _refresh_plan(service, plan)
                        logger.info("Refreshed forecast plan")
                    except Exception:
                        logger.exception(
                            "Failed to refresh forecast plan",
                            extra={
                                "plan_id": plan.id,
                                "organization_id": plan.organization_id,
                                "budget_id": plan.budget_id,
                            },
                        )
            session.commit()


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
        # TODO[P3][5d]: Externalize refresh cadence into configuration per organization.
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


def get_scheduler_state() -> dict[str, Any]:
    """Return scheduler runtime metadata for diagnostics and health checks."""

    with _scheduler_lock:
        scheduler = _scheduler
        if scheduler is None:
            return {"running": False, "jobs": 0, "next_run": None}
        jobs = scheduler.get_jobs()
        next_run = None
        for job in jobs:
            if job.next_run_time is None:
                continue
            if next_run is None or job.next_run_time < next_run:
                next_run = job.next_run_time
        return {
            "running": scheduler.running,
            "jobs": len(jobs),
            "next_run": next_run.isoformat() if next_run else None,
        }
