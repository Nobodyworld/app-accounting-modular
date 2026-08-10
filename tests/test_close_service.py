from __future__ import annotations

from datetime import date

import pytest
from apps.api.models.models import AccountingPeriodStatus, CloseCycleStatus
from apps.api.services.close_service import CloseConflictError, CloseService, CloseValidationError

from tests._close_helpers import close_session


def test_period_overlap_cycle_seed_and_legal_transitions() -> None:
    with pytest.raises(CloseValidationError, match="missing an identifier"):
        CloseService._id(None, "Period")
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id
        service = CloseService(session, actors.organization.id, actors.preparer.id)
        period = service.create_period("March 2026", date(2026, 3, 1), date(2026, 3, 31))
        with pytest.raises(CloseConflictError, match="overlaps"):
            service.create_period("March overlap", date(2026, 3, 31), date(2026, 4, 30))

        cycle = service.create_cycle(period.id, "March close", due_date=date(2026, 4, 5))
        assert cycle.status == CloseCycleStatus.DRAFT
        assert len(service.list_checklist(cycle.id)) == 8
        started = service.start(cycle.id, cycle.version)
        assert started.status == CloseCycleStatus.IN_PROGRESS
        assert started.version == 2
        with pytest.raises(CloseConflictError, match="stale"):
            service.start(cycle.id, 1)


def test_reopen_is_explicit_and_invalidates_cycle_version() -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.administrator.id
        service = CloseService(session, actors.organization.id, actors.administrator.id)
        period = service.create_period("April 2026", date(2026, 4, 1), date(2026, 4, 30))
        cycle = service.create_cycle(period.id, "April close")
        cycle.status = CloseCycleStatus.CLOSED
        period.status = AccountingPeriodStatus.CLOSED
        session.add_all([cycle, period])
        session.commit()
        with pytest.raises(ValueError, match="nonempty"):
            service.reopen(cycle.id, cycle.version, "  ")
        reopened = service.reopen(cycle.id, cycle.version, "Post-close adjustment approved")
        assert reopened.status == CloseCycleStatus.IN_PROGRESS
        assert service.require_period(period.id).status == AccountingPeriodStatus.OPEN
        assert reopened.last_reason == "Post-close adjustment approved"


def test_cross_tenant_period_lookup_is_nondisclosing() -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id
        service = CloseService(session, actors.organization.id, actors.preparer.id)
        period = service.create_period("May 2026", date(2026, 5, 1), date(2026, 5, 31))
        other = type(actors.organization)(name="Other tenant")
        session.add(other)
        session.commit()
        session.refresh(other)
        other_service = CloseService(session, other.id, actors.preparer.id)
        with pytest.raises(ValueError, match="not found"):
            other_service.require_period(period.id)
