"""Audit API tests covering tenant isolation and administrator authorization."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from apps.api import db
from apps.api import main as api_main
from apps.api.models.models import AuditAction, AuditLog, Membership, Organization, User
from apps.api.security import get_current_user
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


@contextmanager
def _create_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, dict[str, User], dict[str, int], dict[str, str]]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db.engine = engine
    db.connect_args = {"check_same_thread": False}
    SQLModel.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        first_org = Organization(name="First Org")
        second_org = Organization(name="Second Org")
        session.add_all([first_org, second_org])
        session.commit()
        session.refresh(first_org)
        session.refresh(second_org)
        assert first_org.id is not None
        assert second_org.id is not None

        users = {
            "admin": User(email="admin@example.com", password_hash="stub", is_active=True),
            "member": User(email="member@example.com", password_hash="stub", is_active=True),
            "outsider": User(email="outsider@example.com", password_hash="stub", is_active=True),
            "other_admin": User(email="other-admin@example.com", password_hash="stub", is_active=True),
        }
        session.add_all(list(users.values()))
        session.commit()
        for user in users.values():
            session.refresh(user)
            assert user.id is not None

        session.add_all(
            [
                Membership(
                    user_id=users["admin"].id,
                    organization_id=first_org.id,
                    is_admin=True,
                ),
                Membership(
                    user_id=users["member"].id,
                    organization_id=first_org.id,
                    is_admin=False,
                ),
                Membership(
                    user_id=users["other_admin"].id,
                    organization_id=second_org.id,
                    is_admin=True,
                ),
            ]
        )
        session.add_all(
            [
                AuditLog(
                    ts=datetime(2024, 1, 3, tzinfo=UTC),
                    action=AuditAction.CREATE,
                    entity_name="Invoice",
                    entity_id="1",
                    request_id="first-request",
                    actor_user_id=users["admin"].id,
                    actor_org_id=first_org.id,
                ),
                AuditLog(
                    ts=datetime(2024, 1, 2, tzinfo=UTC),
                    action=AuditAction.UPDATE,
                    entity_name="Payment",
                    entity_id="2",
                    request_id="second-request",
                    actor_user_id=users["member"].id,
                    actor_org_id=first_org.id,
                ),
                AuditLog(
                    ts=datetime(2024, 1, 4, tzinfo=UTC),
                    action=AuditAction.DELETE,
                    entity_name="OtherTenant",
                    entity_id="3",
                    request_id="other-request",
                    actor_user_id=users["other_admin"].id,
                    actor_org_id=second_org.id,
                ),
                AuditLog(
                    ts=datetime(2024, 1, 5, tzinfo=UTC),
                    action=AuditAction.ACCESS,
                    entity_name="Global",
                    entity_id="4",
                    request_id="global-request",
                    actor_user_id=None,
                    actor_org_id=None,
                ),
            ]
        )
        session.commit()

    selected = {"role": "admin"}
    monkeypatch.setattr(api_main, "init_db", lambda: None)
    monkeypatch.setattr(api_main, "start_scheduler", lambda: None)
    monkeypatch.setattr(api_main, "shutdown_scheduler", lambda: None)
    app = api_main.create_app()
    app.dependency_overrides[get_current_user] = lambda: users[selected["role"]]

    ids = {
        "first_org": first_org.id,
        "second_org": second_org.id,
        "other_admin": users["other_admin"].id,
    }
    try:
        with TestClient(app) as client:
            yield client, users, ids, selected
    finally:
        engine.dispose()


def test_audit_api_requires_positive_organization_id(monkeypatch: pytest.MonkeyPatch) -> None:
    with _create_client(monkeypatch) as (client, _, _, _):
        assert client.get("/audit/").status_code == 422
        assert client.get("/audit/", params={"organization_id": 0}).status_code == 422


def test_audit_api_returns_only_admin_tenant_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    with _create_client(monkeypatch) as (client, _, ids, _):
        response = client.get("/audit/", params={"organization_id": ids["first_org"]})
        assert response.status_code == 200
        payload = response.json()
        assert [item["entity_name"] for item in payload] == ["Invoice", "Payment"]
        assert {item["actor_org_id"] for item in payload} == {ids["first_org"]}

        filtered = client.get(
            "/audit/",
            params={
                "organization_id": ids["first_org"],
                "user": ids["other_admin"],
            },
        )
        assert filtered.status_code == 200
        assert filtered.json() == []


def test_audit_api_rejects_member_and_outsider(monkeypatch: pytest.MonkeyPatch) -> None:
    with _create_client(monkeypatch) as (client, _, ids, selected):
        selected["role"] = "member"
        member_response = client.get("/audit/", params={"organization_id": ids["first_org"]})
        assert member_response.status_code == 403
        assert member_response.json()["detail"] == "Organization administrator access is required"

        selected["role"] = "outsider"
        outsider_response = client.get("/audit/", params={"organization_id": ids["first_org"]})
        assert outsider_response.status_code == 403
        assert outsider_response.json()["detail"] == "Not authorized for this organization"


def test_audit_api_rejects_missing_org_and_inverted_dates(monkeypatch: pytest.MonkeyPatch) -> None:
    with _create_client(monkeypatch) as (client, _, ids, _):
        missing = client.get("/audit/", params={"organization_id": 999999})
        assert missing.status_code == 404

        inverted = client.get(
            "/audit/",
            params={
                "organization_id": ids["first_org"],
                "start": "2024-02-01T00:00:00Z",
                "end": "2024-01-01T00:00:00Z",
            },
        )
        assert inverted.status_code == 422
        assert inverted.json()["detail"] == "start must not be after end"
