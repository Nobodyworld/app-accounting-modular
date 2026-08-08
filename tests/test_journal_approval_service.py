from __future__ import annotations

from datetime import date

import pytest
from apps.api.models.models import JournalApprovalDecision, JournalApprovalStatus
from apps.api.services.close_service import CloseConflictError, CloseService
from apps.api.services.ledger_service import LedgerService
from apps.api.services.reconciliation_service import ReconciliationService
from sqlmodel import select

from tests._close_helpers import close_session


def test_approval_is_idempotent_append_only_and_does_not_mutate_journal() -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id and actors.reviewer.id
        close = CloseService(session, actors.organization.id, actors.preparer.id)
        period = close.create_period("October 2026", date(2026, 10, 1), date(2026, 10, 31))
        cycle = close.create_cycle(period.id, "October close")
        ledger = LedgerService(session, actors.organization.id)
        cash = ledger.create_account("Cash", "ASSET", code="1000")
        revenue = ledger.create_account("Revenue", "REVENUE", code="4000")
        transaction = ledger.post_transaction(
            date(2026, 10, 2),
            "Approved sale",
            [
                {"account_id": cash.id, "debit": 50, "credit": 0},
                {"account_id": revenue.id, "debit": 0, "credit": 50},
            ],
        )
        requestor = ReconciliationService(session, actors.organization.id, actors.preparer.id)
        approval = requestor.request_approval(cycle.id, transaction_id=transaction.id)
        duplicate = requestor.request_approval(cycle.id, transaction_id=transaction.id)
        assert duplicate.id == approval.id
        with pytest.raises(CloseConflictError, match="cannot approve"):
            requestor.decide_approval(
                cycle.id,
                approval.id,
                version=approval.version,
                decision=JournalApprovalStatus.APPROVED,
                reason="self",
            )
        reviewer = ReconciliationService(session, actors.organization.id, actors.reviewer.id)
        approved = reviewer.decide_approval(
            cycle.id,
            approval.id,
            version=approval.version,
            decision=JournalApprovalStatus.APPROVED,
            reason="Reviewed supporting documentation",
        )
        repeated = reviewer.decide_approval(
            cycle.id,
            approval.id,
            version=approval.version,
            decision=JournalApprovalStatus.APPROVED,
            reason="duplicate",
        )
        assert approved.id == repeated.id
        assert len(session.exec(select(JournalApprovalDecision)).all()) == 1
        session.refresh(transaction)
        assert transaction.description == "Approved sale"
