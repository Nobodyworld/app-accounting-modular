"""Central accounting-period posting guard."""

from __future__ import annotations

from datetime import date
from typing import Any, cast

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
    stmt = select(AccountingPeriod.id).where(
        AccountingPeriod.organization_id == organization_id,
        AccountingPeriod.status == AccountingPeriodStatus.CLOSED,
        cast(Any, AccountingPeriod.start_date) <= posting_date,
        cast(Any, AccountingPeriod.end_date) >= posting_date,
    )
    if session.exec(stmt).first() is not None:
        raise ClosedPeriodPostingError(posting_date)


__all__ = ["ClosedPeriodPostingError", "ensure_posting_allowed"]
