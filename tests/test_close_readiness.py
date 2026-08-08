from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from apps.api.models.models import CloseTaskControlType
from apps.api.services.close_evidence_service import CloseEvidenceService
from apps.api.services.close_service import CloseConflictError, CloseService
from apps.api.services.ledger_service import LedgerService
from apps.api.services.period_lock import ClosedPeriodPostingError
from apps.api.services.reconciliation_service import ReconciliationService

from tests._close_helpers import close_session


def test_complete_controlled_close_blocks_then_closes_and_reopens() -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id and actors.reviewer.id and actors.administrator.id
        preparer = CloseService(session, actors.organization.id, actors.preparer.id)
        period = preparer.create_period("February 2027", date(2027, 2, 1), date(2027, 2, 28))
        cycle = preparer.create_cycle(period.id, "February close", policy={"variance_review_required": False})
        cycle = preparer.start(cycle.id, cycle.version)
        with pytest.raises(CloseConflictError, match="blockers"):
            preparer.mark_ready(cycle.id, cycle.version)

        ledger = LedgerService(session, actors.organization.id)
        cash = ledger.create_account("Cash", "ASSET", code="1000")
        reconciliation_service = ReconciliationService(session, actors.organization.id, actors.preparer.id)
        reconciliation = reconciliation_service.prepare_reconciliation(
            cycle.id,
            cash.id,
            control_balance=Decimal("0"),
            tolerance=Decimal("0"),
        )
        reviewer_service = ReconciliationService(session, actors.organization.id, actors.reviewer.id)
        reviewer_service.approve_reconciliation(cycle.id, reconciliation.id, version=reconciliation.version)

        attestation = next(
            task for task in preparer.list_checklist(cycle.id) if task.control_type == CloseTaskControlType.ATTESTATION
        )
        preparer.update_manual_task(
            cycle.id,
            attestation.id,
            version=attestation.version,
            complete=True,
            notes="Provider and report freshness reviewed",
        )
        readiness = preparer.readiness(cycle.id)
        assert readiness.blocker_count == 0
        assert readiness.evidence_freshness == "MISSING"
        cycle = preparer.require_cycle(cycle.id)
        cycle = preparer.mark_ready(cycle.id, cycle.version)
        evidence_service = CloseEvidenceService(session, actors.organization.id, actors.preparer.id)
        bundle = evidence_service.build_bundle(cycle.id)
        evidence_service.record_generation(cycle.id, bundle)
        administrator = CloseService(session, actors.organization.id, actors.administrator.id)
        cycle = administrator.close(cycle.id, cycle.version)
        closed_readiness = administrator.readiness(cycle.id)
        assert closed_readiness.state == "CLOSED"
        assert closed_readiness.evidence_freshness == "CURRENT"
        assert cycle.approved_at == cycle.closed_at
        with pytest.raises(ClosedPeriodPostingError):
            ledger.post_transaction(date(2027, 2, 14), "Blocked after close", [])
        reopened = administrator.reopen(cycle.id, cycle.version, "Approved post-close adjustment")
        assert administrator.readiness(reopened.id).evidence_freshness == "STALE"
