"""Workflow service regression tests covering validation and reprocessing."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date

import pytest
from apps.api.models.models import (
    AuditLog,
    Organization,
    StagedPosting,
    StagedTransaction,
    Transaction,
    WorkflowStatus,
)
from apps.api.services.ledger_service import LedgerService
from apps.api.services.workflow_service import WorkflowService
from sqlmodel import Session, SQLModel, create_engine, select


@contextmanager
def create_session() -> Iterator[Session]:
    """Build an in-memory database session for isolated workflow tests."""
    # TODO[P3][2d]: Promote this helper to a shared fixture for reuse across modules.
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


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


def test_ingestion_is_idempotent_by_source_reference() -> None:
    with create_session() as session:
        ledger = LedgerService(session)
        cash = ledger.create_account(name="Cash", type="ASSET", code="1000")
        revenue = ledger.create_account(name="Revenue", type="REVENUE", code="4000")
        payload = {
            "date": date(2024, 4, 1),
            "description": "Idempotent invoice",
            "source_reference": "invoice-100",
            "metadata": {"batch": "A"},
            "postings": [
                {"account_id": cash.id, "debit": 125.0, "credit": 0.0},
                {"account_id": revenue.id, "debit": 0.0, "credit": 125.0},
            ],
        }
        service = WorkflowService(session)

        first = service.ingest_transactions([payload], source="billing")
        duplicate = service.ingest_transactions([payload], source="billing")

        assert first[0].id == duplicate[0].id
        assert len(session.exec(select(StagedTransaction)).all()) == 1
        assert len(session.exec(select(StagedPosting)).all()) == 2

        conflicting = {**payload, "description": "Different invoice"}
        with pytest.raises(ValueError, match="already exists with different payload"):
            service.ingest_transactions([conflicting], source="billing")

        assert len(session.exec(select(StagedTransaction)).all()) == 1
        assert len(session.exec(select(StagedPosting)).all()) == 2


def test_ingestion_rolls_back_entire_batch_when_one_payload_is_invalid() -> None:
    with create_session() as session:
        ledger = LedgerService(session)
        cash = ledger.create_account(name="Cash", type="ASSET", code="1000")
        revenue = ledger.create_account(name="Revenue", type="REVENUE", code="4000")
        service = WorkflowService(session)

        with pytest.raises(ValueError, match="posting must be a mapping"):
            service.ingest_transactions(
                [
                    {
                        "date": date(2024, 5, 1),
                        "description": "Valid first item",
                        "postings": [
                            {"account_id": cash.id, "debit": 10.0, "credit": 0.0},
                            {"account_id": revenue.id, "debit": 0.0, "credit": 10.0},
                        ],
                    },
                    {
                        "date": date(2024, 5, 2),
                        "description": "Malformed second item",
                        "postings": ["not-a-posting"],
                    },
                ],
                source="batch",
                chunk_size=1,
            )

        assert session.exec(select(StagedTransaction)).all() == []
        assert session.exec(select(StagedPosting)).all() == []


def test_processing_enforces_organization_isolation_per_transaction() -> None:
    with create_session() as session:
        org_a = Organization(name="Org A")
        org_b = Organization(name="Org B")
        session.add_all([org_a, org_b])
        session.commit()
        session.refresh(org_a)
        session.refresh(org_b)
        assert org_a.id is not None
        assert org_b.id is not None

        ledger_a = LedgerService(session, organization_id=org_a.id)
        ledger_b = LedgerService(session, organization_id=org_b.id)
        cash_a = ledger_a.create_account(name="Cash A", type="ASSET", code="1000")
        revenue_a = ledger_a.create_account(name="Revenue A", type="REVENUE", code="4000")
        cash_b = ledger_b.create_account(name="Cash B", type="ASSET", code="1000")
        revenue_b = ledger_b.create_account(name="Revenue B", type="REVENUE", code="4000")

        service = WorkflowService(session)
        staged = service.ingest_transactions(
            [
                {
                    "date": date(2024, 6, 1),
                    "description": "Org A invoice",
                    "source_reference": "org-a-1",
                    "postings": [
                        {"account_id": cash_a.id, "debit": 50.0, "credit": 0.0},
                        {"account_id": revenue_a.id, "debit": 0.0, "credit": 50.0},
                    ],
                },
                {
                    "date": date(2024, 6, 2),
                    "description": "Org B invoice",
                    "source_reference": "org-b-1",
                    "postings": [
                        {"account_id": cash_b.id, "debit": 75.0, "credit": 0.0},
                        {"account_id": revenue_b.id, "debit": 0.0, "credit": 75.0},
                    ],
                },
                {
                    "date": date(2024, 6, 3),
                    "description": "Cross-org entry",
                    "source_reference": "cross-org-1",
                    "postings": [
                        {"account_id": cash_a.id, "debit": 90.0, "credit": 0.0},
                        {"account_id": revenue_b.id, "debit": 0.0, "credit": 90.0},
                    ],
                },
            ],
            source="tenant-test",
        )

        results = service.process_transactions([item.id for item in staged])
        result_by_id = {result.staged_transaction_id: result for result in results}

        assert result_by_id[staged[0].id].status == WorkflowStatus.POSTED
        assert result_by_id[staged[1].id].status == WorkflowStatus.POSTED
        cross_result = result_by_id[staged[2].id]
        assert cross_result.status == WorkflowStatus.FAILED
        assert cross_result.validation_errors is not None
        assert "single organization" in cross_result.validation_errors[0]

        transaction_a = session.get(Transaction, result_by_id[staged[0].id].transaction_id)
        transaction_b = session.get(Transaction, result_by_id[staged[1].id].transaction_id)
        assert transaction_a is not None
        assert transaction_b is not None
        assert transaction_a.organization_id == org_a.id
        assert transaction_b.organization_id == org_b.id
        assert len(session.exec(select(Transaction)).all()) == 2


def test_posting_commit_failure_rolls_back_one_item_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with create_session() as session:
        ledger = LedgerService(session)
        cash = ledger.create_account(name="Cash", type="ASSET", code="1000")
        revenue = ledger.create_account(name="Revenue", type="REVENUE", code="4000")
        service = WorkflowService(session)
        staged = service.ingest_transactions(
            [
                {
                    "date": date(2024, 7, 1),
                    "description": "First item",
                    "postings": [
                        {"account_id": cash.id, "debit": 20.0, "credit": 0.0},
                        {"account_id": revenue.id, "debit": 0.0, "credit": 20.0},
                    ],
                },
                {
                    "date": date(2024, 7, 2),
                    "description": "Second item",
                    "postings": [
                        {"account_id": cash.id, "debit": 30.0, "credit": 0.0},
                        {"account_id": revenue.id, "debit": 0.0, "credit": 30.0},
                    ],
                },
            ],
            source="commit-test",
        )

        original_commit = session.commit
        failure = {"raised": False}

        def fail_once() -> None:
            if not failure["raised"]:
                failure["raised"] = True
                raise RuntimeError("forced workflow commit failure")
            original_commit()

        monkeypatch.setattr(session, "commit", fail_once)
        results = service.process_transactions([item.id for item in staged])

        assert results[0].status == WorkflowStatus.FAILED
        assert results[0].validation_errors == ["Posting failed: forced workflow commit failure"]
        assert results[0].transaction_id is None
        assert results[1].status == WorkflowStatus.POSTED
        assert results[1].transaction_id is not None
        assert len(session.exec(select(Transaction)).all()) == 1


def test_rejections_and_retries_create_workflow_audit_records() -> None:
    with create_session() as session:
        ledger = LedgerService(session)
        cash = ledger.create_account(name="Cash", type="ASSET", code="1000")
        revenue = ledger.create_account(name="Revenue", type="REVENUE", code="4000")
        service = WorkflowService(session)
        staged = service.ingest_transactions(
            [
                {
                    "date": date(2024, 8, 1),
                    "description": "Retry audit",
                    "source_reference": "retry-1",
                    "postings": [
                        {"account_id": 9999, "debit": 45.0, "credit": 0.0},
                        {"account_id": cash.id, "debit": 0.0, "credit": 45.0},
                    ],
                }
            ],
            source="retry-test",
        )[0]

        rejected = service.process_transactions([staged.id])
        assert rejected[0].status == WorkflowStatus.FAILED

        posting = session.exec(
            select(StagedPosting).where(
                StagedPosting.staged_transaction_id == staged.id,
                StagedPosting.debit > 0,
            )
        ).one()
        posting.account_id = revenue.id
        session.add(posting)
        session.commit()

        retried = service.process_transactions([staged.id])
        assert retried[0].status == WorkflowStatus.POSTED

        audit_events = [
            (entry.context or {}).get("event")
            for entry in session.exec(
                select(AuditLog).where(AuditLog.entity_name == "StagedTransaction")
            ).all()
        ]
        assert "rejected" in audit_events
        assert "retried" in audit_events

        transaction_audits = session.exec(
            select(AuditLog).where(AuditLog.entity_name == "Transaction")
        ).all()
        assert len(transaction_audits) == 1
        assert (transaction_audits[0].context or {})["staged_transaction_id"] == staged.id
