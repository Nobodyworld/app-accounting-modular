"""Central accounting-period posting guard."""

from __future__ import annotations

from datetime import date
from typing import Any, cast

from sqlalchemy import update
from sqlmodel import Session, select

from ..models.models import AccountingPeriod, AccountingPeriodStatus, CloseCycle, CloseCycleStatus


class PeriodPostingError(ValueError):
    """Base class for stable period posting conflicts."""

    code = "ACCOUNTING_PERIOD_POSTING_CONFLICT"


class ClosedPeriodPostingError(PeriodPostingError):
    """Stable service error raised before any posting mutation."""

    code = "ACCOUNTING_PERIOD_CLOSED"

    def __init__(self, posting_date: date):
        super().__init__(f"Posting date {posting_date.isoformat()} falls within a closed accounting period")
        self.posting_date = posting_date


class ReadyPeriodPostingError(PeriodPostingError):
    """Posting is frozen while the period's close awaits final approval."""

    code = "ACCOUNTING_PERIOD_CLOSE_READY"

    def __init__(self, posting_date: date):
        super().__init__(
            f"Posting date {posting_date.isoformat()} belongs to a close cycle awaiting final approval; "
            "an administrator must return the cycle to work before posting"
        )
        self.posting_date = posting_date


class PeriodActivityConflictError(PeriodPostingError):
    """The authoritative ledger activity revision changed concurrently."""

    code = "ACCOUNTING_PERIOD_ACTIVITY_CONFLICT"


def _open_period_for_posting(session: Session, organization_id: int, posting_date: date) -> AccountingPeriod | None:
    bounds = (
        AccountingPeriod.organization_id == organization_id,
        cast(Any, AccountingPeriod.start_date) <= posting_date,
        cast(Any, AccountingPeriod.end_date) >= posting_date,
    )
    closed = session.exec(
        select(AccountingPeriod.id).where(*bounds, AccountingPeriod.status == AccountingPeriodStatus.CLOSED)
    ).first()
    if closed is not None:
        raise ClosedPeriodPostingError(posting_date)
    return session.exec(
        select(AccountingPeriod)
        .where(*bounds, AccountingPeriod.status == AccountingPeriodStatus.OPEN)
        .order_by(cast(Any, AccountingPeriod.id))
    ).first()


def _reject_ready_cycle(session: Session, period: AccountingPeriod, posting_date: date) -> None:
    ready = session.exec(
        select(CloseCycle.id).where(
            CloseCycle.organization_id == period.organization_id,
            CloseCycle.period_id == period.id,
            CloseCycle.status == CloseCycleStatus.READY_FOR_APPROVAL,
        )
    ).first()
    if ready is not None:
        raise ReadyPeriodPostingError(posting_date)


def ensure_posting_allowed(session: Session, organization_id: int | None, posting_date: date) -> None:
    """Reject closed/ready inclusive periods without changing activity revision."""

    if organization_id is None:
        return
    acquire_period_write_gate(session, organization_id)
    period = _open_period_for_posting(session, organization_id, posting_date)
    if period is not None:
        _reject_ready_cycle(session, period, posting_date)


def record_posting_activity(session: Session, organization_id: int | None, posting_date: date) -> int | None:
    """Authorize a journal and atomically advance its open period's ledger revision.

    The caller must invoke this after journal validation but before adding the
    transaction. The revision update and journal/audit rows then share the
    caller's transaction, so rollback removes all of them together.
    """

    if organization_id is None:
        return None
    acquire_period_write_gate(session, organization_id)
    period = _open_period_for_posting(session, organization_id, posting_date)
    if period is None:
        return None
    _reject_ready_cycle(session, period, posting_date)
    expected = period.ledger_activity_revision
    result = session.exec(
        update(AccountingPeriod)
        .where(
            cast(Any, AccountingPeriod.id) == period.id,
            cast(Any, AccountingPeriod.organization_id) == organization_id,
            cast(Any, AccountingPeriod.status) == AccountingPeriodStatus.OPEN,
            cast(Any, AccountingPeriod.ledger_activity_revision) == expected,
        )
        .values(ledger_activity_revision=expected + 1)
        .execution_options(synchronize_session=False)
    )
    if getattr(result, "rowcount", 0) != 1:
        session.rollback()
        raise PeriodActivityConflictError("Accounting period ledger activity revision changed concurrently")
    session.expire(period)
    session.refresh(period)
    return period.ledger_activity_revision


def acquire_period_write_gate(session: Session, organization_id: int) -> None:
    """Serialize SQLite close/post writers through the tenant's period rows.

    SQLite permits only one writer. A no-op UPDATE acquires that database write
    position before either operation evaluates the period state. Deployments on
    multi-writer databases should replace this with row-level ``FOR UPDATE`` or
    an equivalent database-native posting gate.
    """

    session.exec(
        update(AccountingPeriod)
        .where(cast(Any, AccountingPeriod.organization_id) == organization_id)
        .values(updated_at=AccountingPeriod.updated_at)
        .execution_options(synchronize_session=False)
    )


__all__ = [
    "ClosedPeriodPostingError",
    "PeriodActivityConflictError",
    "PeriodPostingError",
    "ReadyPeriodPostingError",
    "acquire_period_write_gate",
    "ensure_posting_allowed",
    "record_posting_activity",
]
