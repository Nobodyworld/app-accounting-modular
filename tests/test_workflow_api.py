from __future__ import annotations

import pytest

pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select

from apps.api import db
from apps.api.models.models import StagedPosting, WorkflowStatus
from apps.api.services.ledger_service import LedgerService
from apps.api.main import create_app


def create_client() -> tuple[TestClient, Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    db.engine = engine
    db.connect_args = {"check_same_thread": False}
    SQLModel.metadata.create_all(engine)
    app = create_app()
    return TestClient(app), Session(engine)


def test_workflow_api_end_to_end() -> None:
    client, session = create_client()
    with session:
        ledger = LedgerService(session)
        cash = ledger.create_account(name="Cash", type="ASSET", code="1000")
        revenue = ledger.create_account(name="Revenue", type="REVENUE", code="4000")

    payload = {
        "source": "test_api",
        "source_reference": "batch-1",
        "metadata": {"uploaded_by": "unit"},
        "transactions": [
            {
                "date": "2024-04-01",
                "description": "Invoice",
                "postings": [
                    {"account_id": cash.id, "debit": 200.0, "credit": 0.0},
                    {"account_id": revenue.id, "debit": 0.0, "credit": 200.0},
                ],
            },
            {
                "date": "2024-04-02",
                "description": "Broken entry",
                "postings": [
                    {"account_id": 9999, "debit": 200.0, "credit": 0.0},
                    {"account_id": cash.id, "debit": 0.0, "credit": 200.0},
                ],
            },
        ],
    }

    response = client.post("/workflow/ingest", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["staged_ids"]) == 2
    assert len(data["results"]) == 2

    posted = next(r for r in data["results"] if r["status"] == WorkflowStatus.POSTED.value)
    failed = next(r for r in data["results"] if r["status"] == WorkflowStatus.FAILED.value)
    assert "account 9999 not found" in failed["validation_errors"][0]

    with Session(db.engine) as session:
        posting = session.exec(
            select(StagedPosting).where(
                StagedPosting.staged_transaction_id == failed["staged_transaction_id"],
                StagedPosting.debit > 0,
            )
        ).one()
        posting.account_id = revenue.id
        session.add(posting)
        session.commit()

    process_response = client.post(
        "/workflow/process", json={"staged_ids": [failed["staged_transaction_id"]]}
    )
    assert process_response.status_code == 200
    processed = process_response.json()
    assert processed[0]["status"] == WorkflowStatus.POSTED.value

    detail_response = client.get(f"/workflow/{failed['staged_transaction_id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["status"] == WorkflowStatus.POSTED.value
    assert len(detail["postings"]) == 2

    list_response = client.get("/workflow")
    assert list_response.status_code == 200
    listing = list_response.json()
    assert len(listing) >= 2
