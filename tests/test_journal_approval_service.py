from __future__ import annotations

from datetime import date

import apps.api.services.reconciliation_service as reconciliation_module
import pytest
from apps.api.models.models import JournalApproval, JournalApprovalDecision, JournalApprovalStatus
from apps.api.services.close_service import CloseConflictError, CloseService, CloseValidationError
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
        cycle = close.start(cycle.id, cycle.version)
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


def test_approval_cap_list_pages_and_decision_history_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reconciliation_module, "MAX_JOURNAL_APPROVALS_PER_CYCLE", 2)
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id and actors.reviewer.id
        close = CloseService(session, actors.organization.id, actors.preparer.id)
        period = close.create_period("November 2026", date(2026, 11, 1), date(2026, 11, 30))
        cycle = close.create_cycle(period.id, "November close")
        cycle = close.start(cycle.id, cycle.version)
        ledger = LedgerService(session, actors.organization.id)
        cash = ledger.create_account("Cash", "ASSET", code="1000")
        revenue = ledger.create_account("Revenue", "REVENUE", code="4000")
        transactions = [
            ledger.post_transaction(
                date(2026, 11, day),
                f"Sale {day}",
                [
                    {"account_id": cash.id, "debit": day, "credit": 0},
                    {"account_id": revenue.id, "debit": 0, "credit": day},
                ],
            )
            for day in (2, 3, 4)
        ]
        requestor = ReconciliationService(session, actors.organization.id, actors.preparer.id)
        approvals = [requestor.request_approval(cycle.id, transaction_id=item.id) for item in transactions[:2]]
        assert requestor.request_approval(cycle.id, transaction_id=transactions[0].id).id == approvals[0].id
        with pytest.raises(CloseValidationError, match="Maximum journal approvals"):
            requestor.request_approval(cycle.id, transaction_id=transactions[2].id)
        assert len(session.exec(select(JournalApproval)).all()) == 2

        first_page = requestor.list_approvals(cycle.id, limit=1, offset=0)
        second_page = requestor.list_approvals(cycle.id, limit=1, offset=1)
        assert [item.id for item in first_page + second_page] == [item.id for item in approvals]

        reviewer = ReconciliationService(session, actors.organization.id, actors.reviewer.id)
        rejected = reviewer.decide_approval(
            cycle.id,
            approvals[0].id,
            version=approvals[0].version,
            decision=JournalApprovalStatus.REJECTED,
            reason="Needs support",
        )
        assert rejected.status == JournalApprovalStatus.REJECTED
        rerequested = requestor.request_approval(cycle.id, transaction_id=transactions[0].id, reason="Support added")
        reviewer.decide_approval(
            cycle.id,
            rerequested.id,
            version=rerequested.version,
            decision=JournalApprovalStatus.APPROVED,
            reason="Support reviewed",
        )
        history_first = requestor.approval_history(approvals[0].id, cycle_id=cycle.id, limit=2, offset=0)
        history_second = requestor.approval_history(approvals[0].id, cycle_id=cycle.id, limit=2, offset=2)
        assert [item.to_status for item in history_first + history_second] == [
            JournalApprovalStatus.REJECTED,
            JournalApprovalStatus.REQUESTED,
            JournalApprovalStatus.APPROVED,
        ]
        assert len({item.id for item in history_first + history_second}) == 3
