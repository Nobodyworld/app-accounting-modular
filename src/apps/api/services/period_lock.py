"""Central accounting-period posting guard."""

from __future__ import annotations

from datetime import date
from typing import Any, cast

from sqlalchemy import update
from sqlmodel import Session, select

from ..models.models import AccountingPeriod, AccountingPeriodStatus


class ClosedPeriodPostingError(ValueError):
    """Stable service error raised before any posting mutation."""

    code = "ACCOUNTING_PERIOD_CLOSED"

    def __init__(self, posting_date: date):
        super().__init__(f"Posting date {posting_date.isoformat()} falls within a closed accounting period")
        self.posting_date = posting_date


def ensure_posting_allowed(session: Session, organization_id: int | None, posting_date: date) -> None:
    """Reject inclusive dates in a closed period before journal/audit mutation."""

    if organization_id is None:
        return
    acquire_period_write_gate(session, organization_id)
    stmt = select(AccountingPeriod.id).where(
        AccountingPeriod.organization_id == organization_id,
        AccountingPeriod.status == AccountingPeriodStatus.CLOSED,
        cast(Any, AccountingPeriod.start_date) <= posting_date,
        cast(Any, AccountingPeriod.end_date) >= posting_date,
    )
    if session.exec(stmt).first() is not None:
        raise ClosedPeriodPostingError(posting_date)


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


__all__ = ["ClosedPeriodPostingError", "acquire_period_write_gate", "ensure_posting_allowed"]
