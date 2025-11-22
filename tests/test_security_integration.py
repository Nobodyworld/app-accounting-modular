"""Integration tests for security flows and permission gating."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from apps.api.db import get_session
from apps.api.main import create_app
from apps.api.models.models import AuditLog, Membership, Organization, User
from apps.api.routers import auth as auth_router
from apps.api.security import create_access_token, create_refresh_token, get_password_hash
from jose import jwt
from apps.api.config import settings
from apps.api.services.ledger_service import LedgerService


@pytest.fixture()
def api_context():
    """Provision a FastAPI test client with isolated in-memory persistence."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    app = create_app()

    def override_get_session():
        with Session(engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)

    auth_router._failed_attempts.clear()
    auth_router._lockouts.clear()
    # TODO - (auth) Add integration coverage once lockouts use shared cache state.

    with Session(engine, expire_on_commit=False) as session:
        org1 = Organization(name="Org One")
        org2 = Organization(name="Org Two")
        session.add_all([org1, org2])
        session.commit()
        session.refresh(org1)
        session.refresh(org2)

        admin = User(
            email="admin@example.com",
            password_hash=get_password_hash("secret"),
        )
        member = User(
            email="member@example.com",
            password_hash=get_password_hash("secret"),
        )
        session.add_all([admin, member])
        session.commit()
        session.refresh(admin)
        session.refresh(member)

        membership_admin = Membership(
            user_id=admin.id,
            organization_id=org1.id,
            is_admin=True,
            can_manage_ledger=True,
            can_manage_fx=True,
            can_manage_market=True,
            can_manage_tax=True,
        )
        membership_member = Membership(
            user_id=member.id,
            organization_id=org1.id,
            can_manage_ledger=True,
        )
        session.add_all([membership_admin, membership_member])
        session.commit()

        ledger1 = LedgerService(session, organization_id=org1.id)
        cash1 = ledger1.create_account(name="Org1 Cash", type="ASSET", code="ORG1CASH")
        revenue1 = ledger1.create_account(name="Org1 Revenue", type="REVENUE", code="ORG1REV")
        ledger1.post_transaction(
            date=date(2024, 1, 1),
            description="Org1 Sale",
            postings=[
                {"account_id": cash1.id, "debit": 100.0, "credit": 0.0},
                {"account_id": revenue1.id, "debit": 0.0, "credit": 100.0},
            ],
        )

        ledger2 = LedgerService(session, organization_id=org2.id)
        cash2 = ledger2.create_account(name="Org2 Cash", type="ASSET", code="ORG2CASH")
        revenue2 = ledger2.create_account(name="Org2 Revenue", type="REVENUE", code="ORG2REV")
        ledger2.post_transaction(
            date=date(2024, 1, 2),
            description="Org2 Sale",
            postings=[
                {"account_id": cash2.id, "debit": 200.0, "credit": 0.0},
                {"account_id": revenue2.id, "debit": 0.0, "credit": 200.0},
            ],
        )

        org1_id = org1.id
        org2_id = org2.id
        admin_id = admin.id
        member_id = member.id

    tokens = {
        "admin": create_access_token({"sub": str(admin_id)}),
        "member": create_access_token({"sub": str(member_id)}),
    }

    return client, {"org1_id": org1_id, "org2_id": org2_id, "tokens": tokens}, engine


def test_requires_authentication(api_context):
    client, ctx, _ = api_context
    response = client.get("/ledger/trial-balance", params={"organization_id": ctx["org1_id"]})
    assert response.status_code == 401


def test_role_based_access_blocks_tax_sync(api_context):
    client, ctx, _ = api_context
    headers = {"Authorization": f"Bearer {ctx['tokens']['member']}"}
    response = client.post(
        "/tax/sync",
        params={"organization_id": ctx["org1_id"]},
        headers=headers,
    )
    assert response.status_code == 403


def test_refresh_token_generation() -> None:
    token = create_refresh_token(123)
    decoded = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    assert decoded["sub"] == "123"
    assert decoded["type"] == "refresh"
    assert "sid" in decoded


def test_login_returns_refresh_token(api_context) -> None:
    client, _, _ = api_context
    resp = client.post("/auth/token", data={"username": "admin@example.com", "password": "secret"})
    assert resp.status_code == 200
    body = resp.json()
    assert "refresh_token" in body
    assert "session_id" in body
    decoded = jwt.decode(body["refresh_token"], settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    assert decoded["type"] == "refresh"
    assert decoded["sid"] == body["session_id"]


def test_multi_tenant_isolation(api_context):
    client, ctx, _ = api_context
    admin_headers = {"Authorization": f"Bearer {ctx['tokens']['admin']}"}

    response = client.get(
        "/ledger/trial-balance",
        params={"organization_id": ctx["org1_id"]},
        headers=admin_headers,
    )
    assert response.status_code == 200
    rows = response.json()["rows"]
    codes = {row["account_code"] for row in rows}
    assert "ORG1CASH" in codes
    assert "ORG2CASH" not in codes

    forbidden = client.get(
        "/ledger/trial-balance",
        params={"organization_id": ctx["org2_id"]},
        headers=admin_headers,
    )
    assert forbidden.status_code == 403


def test_login_throttling_and_audit_logging(api_context):
    client, _, engine = api_context

    for _ in range(5):
        response = client.post(
            "/auth/token",
            data={"username": "admin@example.com", "password": "wrong"},
        )
        assert response.status_code == 400

    locked = client.post(
        "/auth/token",
        data={"username": "admin@example.com", "password": "wrong"},
    )
    assert locked.status_code == 429

    # Expire lockout and login successfully
    auth_router._lockouts["admin@example.com"] = datetime(2000, 1, 1, tzinfo=UTC)
    success = client.post(
        "/auth/token",
        data={"username": "admin@example.com", "password": "secret"},
    )
    assert success.status_code == 200

    with Session(engine, expire_on_commit=False) as session:
        entries = session.exec(select(AuditLog).where(AuditLog.entity_name == "auth.login")).all()

    assert len(entries) >= 6  # five failures + one success
    statuses = {entry.after_state["success"] for entry in entries}
    assert statuses == {True, False}


def test_lockout_shared_across_clients(api_context) -> None:
    client, _, _ = api_context
    # trigger lockout in first client
    for _ in range(5):
        client.post("/auth/token", data={"username": "member@example.com", "password": "wrong"})
    locked = client.post("/auth/token", data={"username": "member@example.com", "password": "wrong"})
    assert locked.status_code == 429

    # new client instance should still enforce lockout because cache is shared
    second = TestClient(create_app())
    response = second.post("/auth/token", data={"username": "member@example.com", "password": "wrong"})
    assert response.status_code == 429
