from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from apps.api import db
from apps.api.db import get_session
from apps.api.limits import DEFAULT_CLOSE_LIST_PAGE, MAX_CLOSE_LIST_PAGE
from apps.api.main import create_app
from apps.api.models.models import AuditLog, Budget, BudgetLine, CloseEvidence, Membership, Organization, User
from apps.api.security import get_password_hash
from apps.api.services.auth_session_service import AuthSessionService
from apps.api.services.close_evidence_service import CloseEvidenceService
from apps.api.services.ledger_service import LedgerService
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select


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
        other = User(email="close-other@example.test", password_hash=get_password_hash("secret"))
        session.add_all([admin, manager, other])
        session.commit()
        session.refresh(admin)
        session.refresh(manager)
        session.refresh(other)
        session.add_all(
            [
                Membership(user_id=admin.id, organization_id=org1.id, is_admin=True, can_manage_ledger=True),
                Membership(user_id=manager.id, organization_id=org1.id, can_manage_ledger=True),
                Membership(user_id=other.id, organization_id=org2.id, can_manage_ledger=True),
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
        other_pair = AuthSessionService(session).create_session(other)
        context = {
            "org1": org1.id,
            "org2": org2.id,
            "admin": admin_pair.access_token,
            "manager": manager_pair.access_token,
            "other": other_pair.access_token,
            "admin_id": admin.id,
            "manager_id": manager.id,
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


def _create_draft_cycle(client: TestClient, context: dict[str, Any], label: str) -> dict[str, Any]:
    params = {"organization_id": context["org1"]}
    headers = _headers(context["manager"])
    period = client.post(
        "/close/periods",
        params=params,
        headers=headers,
        json={"label": label, "start_date": "2027-01-01", "end_date": "2027-01-31"},
    )
    assert period.status_code == 201, period.text
    cycle = client.post(
        f"/close/periods/{period.json()['id']}/cycles",
        params=params,
        headers=headers,
        json={"name": f"{label} close"},
    )
    assert cycle.status_code == 201, cycle.text
    return cycle.json()


def test_evidence_download_requires_a_current_record_without_failed_side_effects(close_api) -> None:
    client, context = close_api
    cycle = _create_draft_cycle(client, context, "Recorded evidence")
    params = {"organization_id": context["org1"]}
    headers = _headers(context["manager"])
    path = f"/close/cycles/{cycle['id']}/evidence/download"

    missing = client.get(path, params=params, headers=headers)
    assert missing.status_code == 409
    assert missing.json()["detail"]["code"] == "CLOSE_EVIDENCE_NOT_CURRENT"
    with Session(db.engine) as session:
        assert not list(session.exec(select(CloseEvidence)))
        assert not list(session.exec(select(AuditLog).where(AuditLog.entity_name == "CloseEvidence")))

    generated = client.post(f"/close/cycles/{cycle['id']}/evidence", params=params, headers=headers)
    assert generated.status_code == 200, generated.text
    downloaded = client.get(path, params=params, headers=headers)
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.headers["X-Manifest-SHA256"] == generated.json()["manifest_sha256"]

    mutated = client.post(
        f"/close/cycles/{cycle['id']}/checklist",
        params=params,
        headers=headers,
        json={"title": "Mutation after evidence", "required": False},
    )
    assert mutated.status_code == 201, mutated.text
    stale = client.get(path, params=params, headers=headers)
    assert stale.status_code == 409
    with Session(db.engine) as session:
        assert len(list(session.exec(select(CloseEvidence)))) == 1
        assert len(list(session.exec(select(AuditLog).where(AuditLog.entity_name == "CloseEvidence")))) == 1

    regenerated = client.post(f"/close/cycles/{cycle['id']}/evidence", params=params, headers=headers)
    assert regenerated.status_code == 200, regenerated.text
    assert client.get(path, params=params, headers=headers).status_code == 200
    cross_tenant = client.get(
        path,
        params={"organization_id": context["org2"]},
        headers=_headers(context["other"]),
    )
    assert cross_tenant.status_code == 404


def test_evidence_post_uses_one_snapshot_for_response_record_and_audit(close_api, monkeypatch) -> None:
    client, context = close_api
    cycle = _create_draft_cycle(client, context, "Single snapshot")
    params = {"organization_id": context["org1"]}
    headers = _headers(context["manager"])
    build_calls = 0
    original_build = CloseEvidenceService.build_bundle
    original_record = CloseEvidenceService.record_generation

    def counted_build(service, cycle_id):
        nonlocal build_calls
        build_calls += 1
        return original_build(service, cycle_id)

    def record_then_mutate(service, cycle_id, bundle, *, summary=None, commit=True, allow_closed=False):
        record = original_record(
            service,
            cycle_id,
            bundle,
            summary=summary,
            commit=commit,
            allow_closed=allow_closed,
        )
        service.close.create_custom_task(cycle_id, title="Concurrent post-persistence mutation")
        return record

    monkeypatch.setattr(CloseEvidenceService, "build_bundle", counted_build)
    monkeypatch.setattr(CloseEvidenceService, "record_generation", record_then_mutate)
    generated = client.post(f"/close/cycles/{cycle['id']}/evidence", params=params, headers=headers)
    assert generated.status_code == 200, generated.text
    assert build_calls == 1
    response_manifest = generated.json()["manifest_sha256"]

    with Session(db.engine) as session:
        record = session.exec(select(CloseEvidence).where(CloseEvidence.cycle_id == cycle["id"])).one()
        audit = session.exec(
            select(AuditLog).where(AuditLog.entity_name == "CloseEvidence", AuditLog.entity_id == str(record.id))
        ).one()
        assert audit.after_state is not None
        assert response_manifest == record.manifest_sha256 == audit.after_state["manifest_sha256"]
    stale_download = client.get(
        f"/close/cycles/{cycle['id']}/evidence/download",
        params=params,
        headers=headers,
    )
    assert stale_download.status_code == 409


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
        json={"name": "March close"},
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


def test_cycle_policy_override_is_typed_reasoned_and_admin_only(close_api) -> None:
    client, context = close_api
    period = client.post(
        "/close/periods",
        params={"organization_id": context["org1"]},
        headers=_headers(context["admin"]),
        json={"label": "May 2028", "start_date": "2028-05-01", "end_date": "2028-05-31"},
    ).json()
    endpoint = f"/close/periods/{period['id']}/cycles"
    params = {"organization_id": context["org1"]}
    denied = client.post(
        endpoint,
        params=params,
        headers=_headers(context["manager"]),
        json={
            "name": "Manager override",
            "policy": {"variance_review_required": False, "reason": "Manager request"},
        },
    )
    assert denied.status_code == 403
    malformed = client.post(
        endpoint,
        params=params,
        headers=_headers(context["admin"]),
        json={
            "name": "Unknown override",
            "policy": {"variance_review_required": False, "reason": "Admin request", "arbitrary": "unsafe"},
        },
    )
    assert malformed.status_code == 422
    created = client.post(
        endpoint,
        params=params,
        headers=_headers(context["admin"]),
        json={
            "name": "Controlled override",
            "policy": {
                "required_reconciliation_account_ids": [],
                "reconciliation_scope_not_applicable": True,
                "variance_review_required": False,
                "journal_approval_mode": "ALL_PERIOD_TRANSACTIONS",
                "reason": "No applicable reconciliations or budget for this controlled fixture",
            },
        },
    )
    assert created.status_code == 201, created.text
    policy = created.json()["policy"]
    assert policy == {
        "required_reconciliation_account_ids": [],
        "reconciliation_scope_not_applicable": True,
        "variance_review_required": False,
        "journal_approval_mode": "ALL_PERIOD_TRANSACTIONS",
        "override_reason": "No applicable reconciliations or budget for this controlled fixture",
        "overridden_by_user_id": policy["overridden_by_user_id"],
    }
    assert isinstance(policy["overridden_by_user_id"], int)


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
        json={"name": "April close"},
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
    cancelled_payload = cancelled.json()
    denied_restart = client.post(
        f"/close/cycles/{cycle['id']}/restart",
        params={"organization_id": context["org1"]},
        headers=_headers(context["manager"]),
        json={"version": cancelled_payload["version"], "reason": "Manager cannot restart"},
    )
    assert denied_restart.status_code == 403
    restarted = client.post(
        f"/close/cycles/{cycle['id']}/restart",
        params={"organization_id": context["org1"]},
        headers=_headers(context["admin"]),
        json={"version": cancelled_payload["version"], "reason": "Controlled restart"},
    )
    assert restarted.status_code == 200
    assert restarted.json()["status"] == "IN_PROGRESS"
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
        json={"name": "May close"},
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
        json={"name": "September close", "due_date": "2027-10-05"},
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
    approval_list = client.get(
        f"/close/cycles/{cycle['id']}/journal-approvals",
        params=params,
        headers=manager_headers,
    )
    assert len(approval_list.json()) == 1
    assert "history" not in approval_list.json()[0]
    history_path = f"/close/cycles/{cycle['id']}/journal-approvals/{approval_payload['id']}/history"
    history = client.get(history_path, params=params, headers=manager_headers)
    assert history.status_code == 200 and len(history.json()) == 1
    assert (
        client.get(
            history_path,
            params={"organization_id": context["org2"]},
            headers=_headers(context["other"]),
        ).status_code
        == 404
    )
    for collection_path in (
        f"/close/cycles/{cycle['id']}/reconciliations",
        f"/close/cycles/{cycle['id']}/variance-reviews",
        f"/close/cycles/{cycle['id']}/journal-approvals",
        history_path,
    ):
        maximum = client.get(
            collection_path,
            params={**params, "limit": MAX_CLOSE_LIST_PAGE, "offset": 0},
            headers=manager_headers,
        )
        assert maximum.status_code == 200, maximum.text
        too_large = client.get(
            collection_path,
            params={**params, "limit": MAX_CLOSE_LIST_PAGE + 1, "offset": 0},
            headers=manager_headers,
        )
        assert too_large.status_code == 422
    assert DEFAULT_CLOSE_LIST_PAGE < MAX_CLOSE_LIST_PAGE

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
    returned = client.post(
        f"/close/cycles/{cycle['id']}/return-to-work",
        params=params,
        headers=admin_headers,
        json={"version": cycle["version"], "reason": "One final evidence correction"},
    )
    assert returned.status_code == 200
    returned_readiness = client.get(
        f"/close/cycles/{cycle['id']}/readiness", params=params, headers=manager_headers
    ).json()
    assert returned_readiness["blocker_count"] == 0
    cycle = client.post(
        f"/close/cycles/{cycle['id']}/ready",
        params=params,
        headers=manager_headers,
        json={"version": returned_readiness["version"]},
    ).json()
    preview = client.get(f"/close/cycles/{cycle['id']}/evidence/preview", params=params, headers=manager_headers)
    assert preview.status_code == 200 and preview.json()["freshness"] == "MISSING"
    generated = client.post(f"/close/cycles/{cycle['id']}/evidence", params=params, headers=manager_headers)
    assert generated.status_code == 200, generated.text
    manifest = generated.json()["manifest_sha256"]
    with Session(db.engine, expire_on_commit=False) as evidence_session:
        rebuilt = CloseEvidenceService(
            evidence_session,
            context["org1"],
            context["manager_id"],
        ).build_bundle(cycle["id"])
    response_files = {item["name"]: item["sha256"] for item in generated.json()["files"]}
    differing_files = [item.name for item in rebuilt.files if response_files[item.name] != item.sha256]
    assert rebuilt.manifest_sha256 == manifest, differing_files
    downloaded = client.get(f"/close/cycles/{cycle['id']}/evidence/download", params=params, headers=manager_headers)
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.headers["X-Manifest-SHA256"] == manifest
    cycle = client.post(
        f"/close/cycles/{cycle['id']}/close",
        params=params,
        headers=admin_headers,
        json={"version": cycle["version"]},
    ).json()
    final_preview = client.get(
        f"/close/cycles/{cycle['id']}/evidence/preview", params=params, headers=manager_headers
    ).json()
    assert final_preview["freshness"] == "CURRENT"
    assert final_preview["source_revision"] == cycle["content_revision"]
    reopened = client.post(
        f"/close/cycles/{cycle['id']}/reopen",
        params=params,
        headers=admin_headers,
        json={"version": cycle["version"], "reason": "Controlled API reopen"},
    )
    assert reopened.status_code == 200
    reopened_download = client.get(
        f"/close/cycles/{cycle['id']}/evidence/download",
        params=params,
        headers=manager_headers,
    )
    assert reopened_download.status_code == 409
    assert reopened_download.json()["detail"]["code"] == "CLOSE_EVIDENCE_NOT_CURRENT"


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
