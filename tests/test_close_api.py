from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from apps.api import db
from apps.api.db import get_session
from apps.api.main import create_app
from apps.api.models.models import Budget, BudgetLine, Membership, Organization, User
from apps.api.security import get_password_hash
from apps.api.services.auth_session_service import AuthSessionService
from apps.api.services.ledger_service import LedgerService
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture()
def close_api() -> Iterator[tuple[TestClient, dict[str, Any]]]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    db.engine = engine
    app = create_app()

    def override_get_session() -> Iterator[Session]:
        with Session(engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    with Session(engine, expire_on_commit=False) as session:
        org1 = Organization(name="Close API Org")
        org2 = Organization(name="Other Org")
        session.add_all([org1, org2])
        session.commit()
        session.refresh(org1)
        session.refresh(org2)
        admin = User(email="close-admin@example.test", password_hash=get_password_hash("secret"))
        manager = User(email="close-manager@example.test", password_hash=get_password_hash("secret"))
        session.add_all([admin, manager])
        session.commit()
        session.refresh(admin)
        session.refresh(manager)
        session.add_all(
            [
                Membership(user_id=admin.id, organization_id=org1.id, is_admin=True, can_manage_ledger=True),
                Membership(user_id=manager.id, organization_id=org1.id, can_manage_ledger=True),
            ]
        )
        session.commit()
        ledger = LedgerService(session, org1.id)
        cash = ledger.create_account("Close cash", "ASSET", code="1000")
        revenue = ledger.create_account("Close revenue", "REVENUE", code="4000")
        transaction = ledger.post_transaction(
            date(2027, 9, 10),
            "Close API revenue",
            [
                {"account_id": cash.id, "debit": 200, "credit": 0},
                {"account_id": revenue.id, "debit": 0, "credit": 200},
            ],
        )
        budget = Budget(
            organization_id=org1.id,
            name="Close API budget",
            start_date=date(2027, 9, 1),
            end_date=date(2027, 9, 30),
        )
        session.add(budget)
        session.commit()
        session.refresh(budget)
        session.add(
            BudgetLine(
                budget_id=budget.id,
                account_id=revenue.id,
                period_start=date(2027, 9, 1),
                amount=-100,
            )
        )
        session.commit()
        admin_pair = AuthSessionService(session).create_session(admin)
        manager_pair = AuthSessionService(session).create_session(manager)
        context = {
            "org1": org1.id,
            "org2": org2.id,
            "admin": admin_pair.access_token,
            "manager": manager_pair.access_token,
            "cash": cash.id,
            "revenue": revenue.id,
            "transaction": transaction.id,
            "budget": budget.id,
        }
    client = TestClient(app)
    try:
        yield client, context
    finally:
        client.close()
        engine.dispose()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_close_api_authentication_lifecycle_and_readiness(close_api) -> None:
    client, context = close_api
    assert client.get("/close/periods", params={"organization_id": context["org1"]}).status_code == 401
    created = client.post(
        "/close/periods",
        params={"organization_id": context["org1"]},
        headers=_headers(context["manager"]),
        json={"label": "March 2027", "start_date": "2027-03-01", "end_date": "2027-03-31"},
    )
    assert created.status_code == 201, created.text
    period_id = created.json()["id"]
    cycle_response = client.post(
        f"/close/periods/{period_id}/cycles",
        params={"organization_id": context["org1"]},
        headers=_headers(context["manager"]),
        json={"name": "March close", "policy": {}},
    )
    assert cycle_response.status_code == 201, cycle_response.text
    cycle = cycle_response.json()
    assert (
        len(
            client.get(
                f"/close/periods/{period_id}/cycles",
                params={"organization_id": context["org1"]},
                headers=_headers(context["manager"]),
            ).json()
        )
        == 1
    )
    started = client.post(
        f"/close/cycles/{cycle['id']}/start",
        params={"organization_id": context["org1"]},
        headers=_headers(context["manager"]),
        json={"version": cycle["version"]},
    )
    assert started.status_code == 200
    readiness = client.get(
        f"/close/cycles/{cycle['id']}/readiness",
        params={"organization_id": context["org1"]},
        headers=_headers(context["manager"]),
    )
    assert readiness.status_code == 200
    payload = readiness.json()
    assert payload["state"] == "BLOCKED"
    assert payload["blocker_count"] >= 1
    assert payload["blockers_by_category"]


def test_admin_only_transition_and_nondisclosing_object_scope(close_api) -> None:
    client, context = close_api
    created = client.post(
        "/close/periods",
        params={"organization_id": context["org1"]},
        headers=_headers(context["admin"]),
        json={"label": "April 2027", "start_date": "2027-04-01", "end_date": "2027-04-30"},
    ).json()
    cycle = client.post(
        f"/close/periods/{created['id']}/cycles",
        params={"organization_id": context["org1"]},
        headers=_headers(context["admin"]),
        json={"name": "April close", "policy": {}},
    ).json()
    denied = client.post(
        f"/close/cycles/{cycle['id']}/cancel",
        params={"organization_id": context["org1"]},
        headers=_headers(context["manager"]),
        json={"version": cycle["version"], "reason": "Manager cannot cancel"},
    )
    assert denied.status_code == 403
    cancelled = client.post(
        f"/close/cycles/{cycle['id']}/cancel",
        params={"organization_id": context["org1"]},
        headers=_headers(context["admin"]),
        json={"version": cycle["version"], "reason": "Controlled cancellation"},
    )
    assert cancelled.status_code == 200
    missing = client.get(
        "/close/periods/999999",
        params={"organization_id": context["org1"]},
        headers=_headers(context["admin"]),
    )
    assert missing.status_code == 404
    assert "traceback" not in missing.text.lower()


def test_close_api_rejects_overlap_and_stale_version(close_api) -> None:
    client, context = close_api
    first = client.post(
        "/close/periods",
        params={"organization_id": context["org1"]},
        headers=_headers(context["manager"]),
        json={"label": "May 2027", "start_date": "2027-05-01", "end_date": "2027-05-31"},
    )
    overlap = client.post(
        "/close/periods",
        params={"organization_id": context["org1"]},
        headers=_headers(context["manager"]),
        json={"label": "Overlap", "start_date": "2027-05-31", "end_date": "2027-06-30"},
    )
    assert first.status_code == 201
    assert overlap.status_code == 409
    assert overlap.json()["detail"]["code"] == "CLOSE_CONFLICT"
    period_id = first.json()["id"]
    cycle = client.post(
        f"/close/periods/{period_id}/cycles",
        params={"organization_id": context["org1"]},
        headers=_headers(context["manager"]),
        json={"name": "May close", "policy": {}},
    ).json()
    stale = client.post(
        f"/close/cycles/{cycle['id']}/start",
        params={"organization_id": context["org1"]},
        headers=_headers(context["manager"]),
        json={"version": 999},
    )
    assert stale.status_code == 409


def test_complete_close_control_surface_and_evidence_download(close_api) -> None:
    client, context = close_api
    manager_headers = _headers(context["manager"])
    admin_headers = _headers(context["admin"])
    params = {"organization_id": context["org1"]}
    period = client.post(
        "/close/periods",
        params=params,
        headers=manager_headers,
        json={"label": "September 2027", "start_date": "2027-09-01", "end_date": "2027-09-30"},
    ).json()
    cycle = client.post(
        f"/close/periods/{period['id']}/cycles",
        params=params,
        headers=manager_headers,
        json={"name": "September close", "policy": {}, "due_date": "2027-10-05"},
    ).json()
    cycle = client.post(
        f"/close/cycles/{cycle['id']}/start",
        params=params,
        headers=manager_headers,
        json={"version": cycle["version"]},
    ).json()
    assert client.get(f"/close/cycles/{cycle['id']}", params=params, headers=manager_headers).status_code == 200

    custom = client.post(
        f"/close/cycles/{cycle['id']}/checklist",
        params=params,
        headers=manager_headers,
        json={"title": "Archive supporting schedule", "required": False},
    )
    assert custom.status_code == 201
    custom_payload = custom.json()
    assert (
        client.patch(
            f"/close/cycles/{cycle['id']}/checklist/{custom_payload['id']}",
            params=params,
            headers=manager_headers,
            json={"version": custom_payload["version"], "complete": True, "notes": "Archived"},
        ).status_code
        == 200
    )

    reconciliation = client.post(
        f"/close/cycles/{cycle['id']}/reconciliations",
        params=params,
        headers=manager_headers,
        json={
            "account_id": context["cash"],
            "control_balance": "200.00",
            "tolerance": "0.00",
            "notes": "Matched to statement",
            "evidence_metadata": {"reference": "controlled-statement"},
        },
    )
    assert reconciliation.status_code == 201, reconciliation.text
    reconciliation_payload = reconciliation.json()
    updated_reconciliation = client.patch(
        f"/close/cycles/{cycle['id']}/reconciliations/{reconciliation_payload['id']}",
        params=params,
        headers=manager_headers,
        json={
            "account_id": context["cash"],
            "control_balance": "200.00",
            "tolerance": "0.00",
            "notes": "Matched and refreshed",
            "evidence_metadata": {},
            "version": reconciliation_payload["version"],
        },
    )
    assert updated_reconciliation.status_code == 200
    reconciliation_payload = updated_reconciliation.json()
    approved_reconciliation = client.post(
        f"/close/cycles/{cycle['id']}/reconciliations/{reconciliation_payload['id']}/approve",
        params=params,
        headers=admin_headers,
        json={"version": reconciliation_payload["version"]},
    )
    assert approved_reconciliation.status_code == 200
    assert (
        len(client.get(f"/close/cycles/{cycle['id']}/reconciliations", params=params, headers=manager_headers).json())
        == 1
    )

    variance_rows = client.post(
        f"/close/cycles/{cycle['id']}/variance-reviews/from-budget",
        params=params,
        headers=manager_headers,
        json={
            "budget_id": context["budget"],
            "horizon": 30,
            "absolute_threshold": "50.00",
            "percentage_threshold": "0.10",
            "refresh": True,
        },
    )
    assert variance_rows.status_code == 200, variance_rows.text
    variance = variance_rows.json()[0]
    disposition = client.patch(
        f"/close/cycles/{cycle['id']}/variance-reviews/{variance['id']}",
        params=params,
        headers=manager_headers,
        json={
            "version": variance["version"],
            "disposition": "EXPLAINED",
            "note": "Controlled revenue outperformance",
        },
    )
    assert disposition.status_code == 200
    assert (
        client.get(f"/close/cycles/{cycle['id']}/variance-reviews", params=params, headers=manager_headers).status_code
        == 200
    )

    approval = client.post(
        f"/close/cycles/{cycle['id']}/journal-approvals",
        params=params,
        headers=manager_headers,
        json={"transaction_id": context["transaction"], "reason": "Review journal"},
    )
    assert approval.status_code == 201
    approval_payload = approval.json()
    decided = client.post(
        f"/close/cycles/{cycle['id']}/journal-approvals/{approval_payload['id']}/decide",
        params=params,
        headers=admin_headers,
        json={"version": approval_payload["version"], "decision": "APPROVED", "reason": "Reviewed"},
    )
    assert decided.status_code == 200
    assert (
        len(client.get(f"/close/cycles/{cycle['id']}/journal-approvals", params=params, headers=manager_headers).json())
        == 1
    )

    checklist = client.get(f"/close/cycles/{cycle['id']}/checklist", params=params, headers=manager_headers).json()
    attestation = next(row for row in checklist if row["control_type"] == "ATTESTATION")
    assert (
        client.patch(
            f"/close/cycles/{cycle['id']}/checklist/{attestation['id']}",
            params=params,
            headers=manager_headers,
            json={
                "version": attestation["version"],
                "complete": True,
                "notes": "Freshness reviewed",
                "owner_user_id": attestation["owner_user_id"],
                "due_date": attestation["due_date"],
            },
        ).status_code
        == 200
    )
    readiness = client.get(f"/close/cycles/{cycle['id']}/readiness", params=params, headers=manager_headers).json()
    assert readiness["blocker_count"] == 0
    cycle = client.post(
        f"/close/cycles/{cycle['id']}/ready",
        params=params,
        headers=manager_headers,
        json={"version": readiness["version"]},
    ).json()
    preview = client.get(f"/close/cycles/{cycle['id']}/evidence/preview", params=params, headers=manager_headers)
    assert preview.status_code == 200 and preview.json()["freshness"] == "MISSING"
    generated = client.post(f"/close/cycles/{cycle['id']}/evidence", params=params, headers=manager_headers)
    assert generated.status_code == 200, generated.text
    manifest = generated.json()["manifest_sha256"]
    downloaded = client.get(f"/close/cycles/{cycle['id']}/evidence/download", params=params, headers=manager_headers)
    assert downloaded.status_code == 200
    assert downloaded.headers["X-Manifest-SHA256"] == manifest
    cycle = client.post(
        f"/close/cycles/{cycle['id']}/close",
        params=params,
        headers=admin_headers,
        json={"version": cycle["version"]},
    ).json()
    reopened = client.post(
        f"/close/cycles/{cycle['id']}/reopen",
        params=params,
        headers=admin_headers,
        json={"version": cycle["version"], "reason": "Controlled API reopen"},
    )
    assert reopened.status_code == 200


def test_close_route_errors_are_typed_across_control_surface(close_api) -> None:
    client, context = close_api
    headers = _headers(context["manager"])
    params = {"organization_id": context["org1"]}
    missing = 999_999
    calls = [
        client.get(f"/close/periods/{missing}/cycles", params=params, headers=headers),
        client.get(f"/close/cycles/{missing}", params=params, headers=headers),
        client.get(f"/close/cycles/{missing}/readiness", params=params, headers=headers),
        client.get(f"/close/cycles/{missing}/checklist", params=params, headers=headers),
        client.post(
            f"/close/cycles/{missing}/checklist",
            params=params,
            headers=headers,
            json={"title": "Missing cycle task"},
        ),
        client.patch(
            f"/close/cycles/{missing}/checklist/{missing}",
            params=params,
            headers=headers,
            json={"version": 1, "complete": True},
        ),
        client.get(f"/close/cycles/{missing}/reconciliations", params=params, headers=headers),
        client.post(
            f"/close/cycles/{missing}/reconciliations",
            params=params,
            headers=headers,
            json={"account_id": context["cash"], "control_balance": "0", "tolerance": "0"},
        ),
        client.post(
            f"/close/cycles/{missing}/reconciliations/{missing}/approve",
            params=params,
            headers=headers,
            json={"version": 1},
        ),
        client.get(f"/close/cycles/{missing}/variance-reviews", params=params, headers=headers),
        client.patch(
            f"/close/cycles/{missing}/variance-reviews/{missing}",
            params=params,
            headers=headers,
            json={"version": 1, "disposition": "EXPLAINED", "note": "Reviewed"},
        ),
        client.post(
            f"/close/cycles/{missing}/journal-approvals",
            params=params,
            headers=headers,
            json={"transaction_id": context["transaction"]},
        ),
        client.get(f"/close/cycles/{missing}/journal-approvals", params=params, headers=headers),
        client.post(
            f"/close/cycles/{missing}/journal-approvals/{missing}/decide",
            params=params,
            headers=headers,
            json={"version": 1, "decision": "APPROVED", "reason": "Reviewed"},
        ),
        client.get(f"/close/cycles/{missing}/evidence/preview", params=params, headers=headers),
        client.post(f"/close/cycles/{missing}/evidence", params=params, headers=headers),
        client.get(f"/close/cycles/{missing}/evidence/download", params=params, headers=headers),
    ]
    assert all(response.status_code == 404 for response in calls)
    assert all(response.json()["detail"]["code"] == "CLOSE_NOT_FOUND" for response in calls)
