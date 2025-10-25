"""Workflow service regression tests covering validation and reprocessing."""

from __future__ import annotations

from datetime import date

from sqlmodel import Session, SQLModel, create_engine, select

from apps.api.models.models import StagedPosting, WorkflowStatus
from apps.api.services.ledger_service import LedgerService
from apps.api.services.workflow_service import WorkflowService


def create_session():
    """Build an in-memory database session for isolated workflow tests."""
    # TODO[P3][2d]: Promote this helper to a shared fixture for reuse across modules.
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine, expire_on_commit=False)


def test_workflow_validation_and_reprocessing() -> None:
    with create_session() as session:
        ledger = LedgerService(session)
        cash = ledger.create_account(name="Cash", type="ASSET", code="1000")
        revenue = ledger.create_account(name="Revenue", type="REVENUE", code="4000")

        svc = WorkflowService(session)
        staged = svc.ingest_transactions(
            [
                {
                    "date": date(2024, 3, 1),
                    "description": "Invoice", 
                    "postings": [
                        {"account_id": cash.id, "debit": 250.0, "credit": 0.0},
                        {"account_id": revenue.id, "debit": 0.0, "credit": 250.0},
                    ],
                },
                {
                    "date": date(2024, 3, 2),
                    "description": "Broken entry",
                    "postings": [
                        {"account_id": 9999, "debit": 250.0, "credit": 0.0},
                        {"account_id": cash.id, "debit": 0.0, "credit": 250.0},
                    ],
                },
            ],
            source="pytest",
        )

        results = svc.process_transactions([item.id for item in staged])
        assert len(results) == 2

        result_map = {result.staged_transaction_id: result for result in results}
        assert result_map[staged[0].id].status == WorkflowStatus.POSTED
        failed_result = result_map[staged[1].id]
        assert failed_result.status == WorkflowStatus.FAILED
        assert failed_result.validation_errors is not None
        assert "account 9999 not found" in failed_result.validation_errors[0]

        posting = session.exec(
            select(StagedPosting).where(
                StagedPosting.staged_transaction_id == staged[1].id,
                StagedPosting.debit > 0,
            )
        ).one()
        posting.account_id = revenue.id
        session.add(posting)
        session.commit()

        retry_result = svc.process_transactions([staged[1].id])
        assert retry_result[0].status == WorkflowStatus.POSTED

        repeat = svc.process_transactions([staged[1].id])
        assert repeat[0].status == WorkflowStatus.POSTED
        assert repeat[0].transaction_id == retry_result[0].transaction_id
