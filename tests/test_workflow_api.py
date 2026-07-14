"""Workflow API integration tests exercising tenant-scoped staging and processing."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal

import pytest
from apps.api import db
from apps.api.main import create_app
from apps.api.models.models import (
    Membership,
    Organization,
    StagedPosting,
    StagedTransaction,
    User,
    WorkflowStatus,
)
from apps.api.security import get_current_user
from apps.api.services.ledger_service import LedgerService
from apps.api.services.workflow_service import WorkflowService
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

pytest.importorskip("httpx")


@dataclass(slots=True, frozen=True)
class WorkflowApiContext:
    user_id: int
    organization_id: int
    other_organization_id: int
    cash_id: int
    revenue_id: int
    other_cash_id: int
    other_revenue_id: int


@contextmanager
def create_client(
    *,
    authenticated: bool = True,
    can_manage_ledger: bool = True,
    member_of_other_organization: bool = False,
) -> Iterator[tuple[TestClient, WorkflowApiContext]]:
    """Create a FastAPI client with two isolated workflow organizations."""

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db.engine = engine
    db.connect_args = {"check_same_thread": False}
    SQLModel.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        user = User(email="tester@example.com", password_hash="stub", is_active=True)
        organization = Organization(name="Primary Org")
        other_organization = Organization(name="Other Org")
        session.add_all([user, organization, other_organization])
        session.commit()
        session.refresh(user)
        session.refresh(organization)
        session.refresh(other_organization)
        assert user.id is not None
        assert organization.id is not None
        assert other_organization.id is not None

        session.add(
            Membership(
                user_id=user.id,
                organization_id=organization.id,
                can_manage_ledger=can_manage_ledger,
            )
        )
        if member_of_other_organization:
            session.add(
                Membership(
                    user_id=user.id,
                    organization_id=other_organization.id,
                    can_manage_ledger=True,
                )
            )
        session.commit()

        primary_ledger = LedgerService(session, organization_id=organization.id)
        cash = primary_ledger.create_account(name="Cash", type="ASSET", code="1000")
        revenue = primary_ledger.create_account(name="Revenue", type="REVENUE", code="4000")
        other_ledger = LedgerService(session, organization_id=other_organization.id)
        other_cash = other_ledger.create_account(name="Other Cash", type="ASSET", code="1000")
        other_revenue = other_ledger.create_account(name="Other Revenue", type="REVENUE", code="4000")
        assert cash.id is not None
        assert revenue.id is not None
        assert other_cash.id is not None
        assert other_revenue.id is not None

        context = WorkflowApiContext(
            user_id=user.id,
            organization_id=organization.id,
            other_organization_id=other_organization.id,
            cash_id=cash.id,
            revenue_id=revenue.id,
            other_cash_id=other_cash.id,
            other_revenue_id=other_revenue.id,
        )

    app = create_app()
    if authenticated:

        def _stub_user() -> User:
            return User(
                id=context.user_id,
                email="tester@example.com",
                password_hash="stub",
                is_active=True,
            )

        app.dependency_overrides[get_current_user] = _stub_user

    client = TestClient(app)
    try:
        yield client, context
    finally:
        client.close()
        engine.dispose()


def _balanced_transaction(
    context: WorkflowApiContext,
    *,
    description: str = "Invoice",
    source_reference: str | None = None,
    amount: str = "200.00",
) -> dict[str, object]:
    return {
        "date": "2024-04-01",
        "description": description,
        "source_reference": source_reference,
        "postings": [
            {"account_id": context.cash_id, "debit": amount, "credit": "0"},
            {"account_id": context.revenue_id, "debit": "0", "credit": amount},
        ],
    }


def test_workflow_api_end_to_end() -> None:
    with create_client() as (client, context):
        payload = {
            "source": "test_api",
            "source_reference": "batch-1",
            "metadata": {"uploaded_by": "unit"},
            "transactions": [
                _balanced_transaction(context),
                {
                    "date": "2024-04-02",
                    "description": "Broken entry",
                    "postings": [
                        {"account_id": 9999, "debit": "200.00", "credit": "0"},
                        {"account_id": context.cash_id, "debit": "0", "credit": "200.00"},
                    ],
                },
            ],
        }

        response = client.post(
            "/workflow/ingest",
            params={"organization_id": context.organization_id},
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["staged_ids"]) == 2
        assert len(data["results"]) == 2

        failed = next(result for result in data["results"] if result["status"] == WorkflowStatus.FAILED.value)
        assert "account 9999 not found" in failed["validation_errors"][0]

        with Session(db.engine, expire_on_commit=False) as patch_session:
            posting = patch_session.exec(
                select(StagedPosting).where(
                    StagedPosting.staged_transaction_id == failed["staged_transaction_id"],
                    StagedPosting.debit > 0,
                )
            ).one()
            posting.account_id = context.revenue_id
            patch_session.add(posting)
            patch_session.commit()

        process_response = client.post(
            "/workflow/process",
            params={"organization_id": context.organization_id},
            json={"staged_ids": [failed["staged_transaction_id"]]},
        )
        assert process_response.status_code == 200
        processed = process_response.json()
        assert processed[0]["status"] == WorkflowStatus.POSTED.value

        detail_response = client.get(
            f"/workflow/{failed['staged_transaction_id']}",
            params={"organization_id": context.organization_id},
        )
        assert detail_response.status_code == 200
        detail = detail_response.json()
        assert detail["status"] == WorkflowStatus.POSTED.value
        assert detail["source"] == "test_api"
        assert detail["source_metadata"] == {"uploaded_by": "unit"}
        assert len(detail["postings"]) == 2

        list_response = client.get(
            "/workflow",
            params={"organization_id": context.organization_id},
        )
        assert list_response.status_code == 200
        assert len(list_response.json()) == 2


def test_workflow_routes_require_authentication() -> None:
    with create_client(authenticated=False) as (client, context):
        response = client.get(
            "/workflow",
            params={"organization_id": context.organization_id},
        )
        assert response.status_code == 401


def test_workflow_routes_require_membership_and_ledger_permission() -> None:
    with create_client() as (client, context):
        forbidden_org = client.get(
            "/workflow",
            params={"organization_id": context.other_organization_id},
        )
        assert forbidden_org.status_code == 403

    with create_client(can_manage_ledger=False) as (client, context):
        forbidden_permission = client.get(
            "/workflow",
            params={"organization_id": context.organization_id},
        )
        assert forbidden_permission.status_code == 403


def test_cross_organization_account_ids_are_rejected_without_staging() -> None:
    with create_client() as (client, context):
        response = client.post(
            "/workflow/ingest",
            params={"organization_id": context.organization_id},
            json={
                "source": "cross-tenant",
                "transactions": [
                    {
                        "date": "2024-05-01",
                        "description": "Cross tenant",
                        "postings": [
                            {"account_id": context.other_cash_id, "debit": "50", "credit": "0"},
                            {"account_id": context.revenue_id, "debit": "0", "credit": "50"},
                        ],
                    }
                ],
            },
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Account not found"

        with Session(db.engine) as session:
            assert session.exec(select(StagedTransaction)).all() == []


def test_list_get_and_process_hide_other_organization_records() -> None:
    with create_client() as (client, context):
        with Session(db.engine, expire_on_commit=False) as session:
            service = WorkflowService(session)
            other = service.ingest_transactions(
                [
                    {
                        "date": "2024-06-01",
                        "description": "Other tenant record",
                        "postings": [
                            {"account_id": context.other_cash_id, "debit": 10.0, "credit": 0.0},
                            {"account_id": context.other_revenue_id, "debit": 0.0, "credit": 10.0},
                        ],
                        "metadata": {
                            "_organization_id": context.other_organization_id,
                            "_workflow_source": "other",
                        },
                    }
                ],
                source=f"other::organization:{context.other_organization_id}",
            )[0]
            assert other.id is not None
            other_id = other.id

        listing = client.get(
            "/workflow",
            params={"organization_id": context.organization_id},
        )
        assert listing.status_code == 200
        assert listing.json() == []

        detail = client.get(
            f"/workflow/{other_id}",
            params={"organization_id": context.organization_id},
        )
        assert detail.status_code == 404

        process = client.post(
            "/workflow/process",
            params={"organization_id": context.organization_id},
            json={"staged_ids": [other_id]},
        )
        assert process.status_code == 404


def test_empty_process_selection_does_not_process_all_records() -> None:
    with create_client() as (client, context):
        ingest = client.post(
            "/workflow/ingest",
            params={"organization_id": context.organization_id},
            json={
                "source": "manual",
                "auto_process": False,
                "transactions": [_balanced_transaction(context)],
            },
        )
        assert ingest.status_code == 200
        staged_id = ingest.json()["staged_ids"][0]

        process = client.post(
            "/workflow/process",
            params={"organization_id": context.organization_id},
            json={"staged_ids": []},
        )
        assert process.status_code == 200
        assert process.json() == []

        with Session(db.engine) as session:
            staged = session.get(StagedTransaction, staged_id)
            assert staged is not None
            assert staged.status == WorkflowStatus.INGESTED


def test_explicit_idempotency_keys_are_scoped_per_organization() -> None:
    with create_client(member_of_other_organization=True) as (client, context):
        shared_reference = "invoice-100"
        primary = client.post(
            "/workflow/ingest",
            params={"organization_id": context.organization_id},
            json={
                "source": "billing",
                "auto_process": False,
                "transactions": [
                    _balanced_transaction(context, source_reference=shared_reference),
                ],
            },
        )
        assert primary.status_code == 200

        other = client.post(
            "/workflow/ingest",
            params={"organization_id": context.other_organization_id},
            json={
                "source": "billing",
                "auto_process": False,
                "transactions": [
                    {
                        "date": "2024-04-01",
                        "description": "Other invoice",
                        "source_reference": shared_reference,
                        "postings": [
                            {"account_id": context.other_cash_id, "debit": "25", "credit": "0"},
                            {"account_id": context.other_revenue_id, "debit": "0", "credit": "25"},
                        ],
                    }
                ],
            },
        )
        assert other.status_code == 200
        assert primary.json()["staged_ids"][0] != other.json()["staged_ids"][0]


def test_workflow_decimal_round_trip_and_request_boundaries() -> None:
    with create_client() as (client, context):
        empty = client.post(
            "/workflow/ingest",
            params={"organization_id": context.organization_id},
            json={"source": "empty", "transactions": []},
        )
        assert empty.status_code == 422

        invalid_org = client.get("/workflow", params={"organization_id": 0})
        assert invalid_org.status_code == 422

        too_long = client.post(
            "/workflow/ingest",
            params={"organization_id": context.organization_id},
            json={
                "source": "bounds",
                "transactions": [
                    _balanced_transaction(context, description="x" * 256),
                ],
            },
        )
        assert too_long.status_code == 422

        ingest = client.post(
            "/workflow/ingest",
            params={"organization_id": context.organization_id},
            json={
                "source": "decimal",
                "auto_process": False,
                "transactions": [
                    _balanced_transaction(context, amount="0.10"),
                ],
            },
        )
        assert ingest.status_code == 200
        staged_id = ingest.json()["staged_ids"][0]

        detail = client.get(
            f"/workflow/{staged_id}",
            params={"organization_id": context.organization_id},
        )
        assert detail.status_code == 200
        postings = detail.json()["postings"]
        assert Decimal(str(postings[0]["debit"])) == Decimal("0.1")
        assert Decimal(str(postings[1]["credit"])) == Decimal("0.1")
