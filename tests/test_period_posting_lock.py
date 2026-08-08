from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from apps.api.models.models import (
    AccountingPeriodStatus,
    AuditLog,
    CloseTaskControlType,
    JournalEntry,
    StagedTransaction,
    Transaction,
    WorkflowStatus,
)
from apps.api.services.close_evidence_service import CloseEvidenceService
from apps.api.services.close_service import CloseService
from apps.api.services.ledger_service import LedgerService
from apps.api.services.period_lock import ClosedPeriodPostingError, ReadyPeriodPostingError
from apps.api.services.reconciliation_service import ReconciliationService
from apps.api.services.workflow_service import WorkflowService
from sqlmodel import select

from tests._close_helpers import close_session


def test_closed_period_blocks_inclusive_boundaries_without_partial_writes() -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.administrator.id
        close = CloseService(session, actors.organization.id, actors.administrator.id)
        period = close.create_period("June 2026", date(2026, 6, 1), date(2026, 6, 30))
        period.status = AccountingPeriodStatus.CLOSED
        session.add(period)
        session.commit()
        ledger = LedgerService(session, actors.organization.id)
        cash = ledger.create_account("Cash", "ASSET", code="1000")
        revenue = ledger.create_account("Revenue", "REVENUE", code="4000")
        for posting_date in (date(2026, 6, 1), date(2026, 6, 30)):
            with pytest.raises(ClosedPeriodPostingError) as exc_info:
                ledger.post_transaction(
                    posting_date,
                    "Blocked journal",
                    [
                        {"account_id": cash.id, "debit": 10, "credit": 0},
                        {"account_id": revenue.id, "debit": 0, "credit": 10},
                    ],
                )
            assert exc_info.value.code == "ACCOUNTING_PERIOD_CLOSED"
        assert session.exec(select(Transaction)).all() == []
        assert session.exec(select(JournalEntry)).all() == []


def test_reopened_period_allows_normal_posting() -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.administrator.id
        close = CloseService(session, actors.organization.id, actors.administrator.id)
        period = close.create_period("July 2026", date(2026, 7, 1), date(2026, 7, 31))
        ledger = LedgerService(session, actors.organization.id)
        cash = ledger.create_account("Cash", "ASSET", code="1000")
        equity = ledger.create_account("Equity", "EQUITY", code="3000")
        transaction = ledger.post_transaction(
            date(2026, 7, 15),
            "Allowed journal",
            [
                {"account_id": cash.id, "debit": 25, "credit": 0},
                {"account_id": equity.id, "debit": 0, "credit": 25},
            ],
        )
        assert period.status == AccountingPeriodStatus.OPEN
        session.refresh(period)
        assert period.ledger_activity_revision == 2
        assert transaction.id is not None


def test_ready_cycle_freezes_direct_and_workflow_posting_and_new_activity_stales_controls() -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id and actors.reviewer.id and actors.administrator.id
        ledger = LedgerService(session, actors.organization.id)
        cash = ledger.create_account("Revision cash", "ASSET", code="1100")
        revenue = ledger.create_account("Revision revenue", "REVENUE", code="4100")
        preparer = CloseService(session, actors.organization.id, actors.preparer.id)
        admin = CloseService(session, actors.organization.id, actors.administrator.id)
        period = preparer.create_period("Revision period", date(2027, 9, 1), date(2027, 9, 30))
        cycle = admin.create_cycle(
            period.id,
            "Revision close",
            owner_user_id=actors.preparer.id,
            policy={"variance_review_required": False, "override_reason": "Focused revision fixture"},
        )
        cycle = preparer.start(cycle.id, cycle.version)
        ledger.post_transaction(
            date(2027, 9, 10),
            "Initial journal",
            [
                {"account_id": cash.id, "debit": 10, "credit": 0},
                {"account_id": revenue.id, "debit": 0, "credit": 10},
            ],
        )
        session.refresh(period)
        assert period.ledger_activity_revision == 2

        controls = ReconciliationService(session, actors.organization.id, actors.preparer.id)
        reconciliation = controls.prepare_reconciliation(
            cycle.id,
            cash.id,
            control_balance=Decimal("10"),
            tolerance=Decimal("0"),
        )
        ReconciliationService(session, actors.organization.id, actors.reviewer.id).approve_reconciliation(
            cycle.id, reconciliation.id, version=reconciliation.version
        )
        attestation = next(
            task for task in preparer.list_checklist(cycle.id) if task.control_type == CloseTaskControlType.ATTESTATION
        )
        preparer.update_manual_task(cycle.id, attestation.id, version=attestation.version, complete=True)
        cycle = preparer.require_cycle(cycle.id)
        cycle = preparer.mark_ready(cycle.id, cycle.version)
        evidence = CloseEvidenceService(session, actors.organization.id, actors.preparer.id)
        evidence.record_generation(cycle.id, evidence.build_bundle(cycle.id))

        second_postings = [
            {"account_id": cash.id, "debit": 5, "credit": 0},
            {"account_id": revenue.id, "debit": 0, "credit": 5},
        ]
        with pytest.raises(ReadyPeriodPostingError) as direct_error:
            ledger.post_transaction(date(2027, 9, 20), "Frozen direct journal", second_postings)
        assert direct_error.value.code == "ACCOUNTING_PERIOD_CLOSE_READY"

        workflow = WorkflowService(session)
        staged = workflow.ingest_transactions(
            [
                {
                    "date": date(2027, 9, 21),
                    "description": "Frozen workflow journal",
                    "postings": second_postings,
                    "metadata": {"_organization_id": actors.organization.id},
                }
            ],
            source="ready-freeze",
            metadata={"_organization_id": actors.organization.id},
        )[0]
        with pytest.raises(ReadyPeriodPostingError):
            workflow.process_transactions([staged.id])
        session.refresh(period)
        assert period.ledger_activity_revision == 2

        cycle = admin.return_to_work(cycle.id, cycle.version, "Additional journal required")
        ledger.post_transaction(date(2027, 9, 20), "Returned-to-work journal", second_postings)
        session.refresh(period)
        assert period.ledger_activity_revision == 3
        readiness = preparer.readiness(cycle.id)
        assert readiness.evidence_freshness == "STALE"
        assert "RECONCILIATIONS_STALE" in {blocker.code for blocker in readiness.blockers}


@pytest.mark.parametrize("initial_status", [WorkflowStatus.INGESTED, WorkflowStatus.VALIDATED, WorkflowStatus.FAILED])
def test_workflow_auto_post_and_retry_paths_preserve_staged_state_when_period_is_closed(initial_status) -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.administrator.id
        close = CloseService(session, actors.organization.id, actors.administrator.id)
        period = close.create_period("August 2027", date(2027, 8, 1), date(2027, 8, 31))
        ledger = LedgerService(session, actors.organization.id)
        cash = ledger.create_account("Cash", "ASSET", code="1000")
        revenue = ledger.create_account("Revenue", "REVENUE", code="4000")
        workflow = WorkflowService(session)
        staged = workflow.ingest_transactions(
            [
                {
                    "date": date(2027, 8, 15),
                    "description": "Closed workflow journal",
                    "postings": [
                        {"account_id": cash.id, "debit": 10, "credit": 0, "currency": "USD"},
                        {"account_id": revenue.id, "debit": 0, "credit": 10, "currency": "USD"},
                    ],
                }
            ],
            source=f"test::organization:{actors.organization.id}",
            metadata={"_organization_id": actors.organization.id},
        )[0]
        staged.status = initial_status
        session.add(staged)
        period.status = AccountingPeriodStatus.CLOSED
        session.add(period)
        session.commit()
        audit_count = len(session.exec(select(AuditLog)).all())
        with pytest.raises(ClosedPeriodPostingError):
            workflow.process_transactions([staged.id], auto_post=True)
        persisted = session.get(StagedTransaction, staged.id)
        assert persisted is not None and persisted.status == initial_status
        assert persisted.transaction_id is None
        assert session.exec(select(Transaction)).all() == []
        assert len(session.exec(select(AuditLog)).all()) == audit_count
