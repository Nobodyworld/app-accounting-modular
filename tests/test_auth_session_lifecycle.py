"""Deterministic integration coverage for persisted authentication sessions."""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from typing import Any
from uuid import uuid4

import jwt
import pytest
from apps.api import db
from apps.api.config import settings
from apps.api.db import get_session
from apps.api.main import create_app
from apps.api.models.models import AuthSession, Membership, Organization, User
from apps.api.routers import auth as auth_router
from apps.api.security import create_access_token, get_current_user, get_password_hash
from apps.api.services.auth_session_service import AuthSessionService, TokenPair
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select


@pytest.fixture()
def auth_api() -> Iterator[dict[str, Any]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    db.engine = engine
    app = create_app()

    def override_get_session() -> Iterator[Session]:
        with Session(engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    auth_router._failed_attempts.clear()
    auth_router._lockouts.clear()

    with Session(engine, expire_on_commit=False) as session:
        org_one = Organization(name="Session Org One")
        org_two = Organization(name="Session Org Two")
        session.add_all([org_one, org_two])
        session.commit()
        session.refresh(org_one)
        session.refresh(org_two)
        users = {
            "admin": User(email="session-admin@example.com", password_hash=get_password_hash("secret")),
            "member": User(email="session-member@example.com", password_hash=get_password_hash("secret")),
            "other_admin": User(email="other-admin@example.com", password_hash=get_password_hash("secret")),
            "inactive": User(
                email="inactive-session@example.com",
                password_hash=get_password_hash("secret"),
                is_active=False,
            ),
        }
        session.add_all(list(users.values()))
        session.commit()
        for user in users.values():
            session.refresh(user)
        session.add_all(
            [
                Membership(user_id=users["admin"].id, organization_id=org_one.id, is_admin=True),
                Membership(user_id=users["member"].id, organization_id=org_one.id),
                Membership(user_id=users["other_admin"].id, organization_id=org_two.id, is_admin=True),
            ]
        )
        session.commit()
        ids = {name: user.id for name, user in users.items()}
        org_ids = {"one": org_one.id, "two": org_two.id}

    with TestClient(app) as client:
        yield {"client": client, "engine": engine, "ids": ids, "org_ids": org_ids}
    engine.dispose()


def _login(auth_api: dict[str, Any], email: str, password: str = "secret") -> dict[str, str]:
    response = auth_api["client"].post("/auth/token", data={"username": email, "password": password})
    assert response.status_code == 200
    return response.json()


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _decode(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def test_login_persists_exactly_one_session_and_required_claims(auth_api: dict[str, Any]) -> None:
    pair = _login(auth_api, "session-admin@example.com")
    access = _decode(pair["access_token"])
    refresh = _decode(pair["refresh_token"])

    assert access["sid"] == refresh["sid"] == pair["session_id"]
    assert access["jti"] != refresh["jti"]
    assert access["type"] == "access"
    assert refresh["type"] == "refresh"
    assert set(("sub", "sid", "jti", "type", "iat", "exp")) <= access.keys()
    assert set(("sub", "sid", "jti", "type", "iat", "exp")) <= refresh.keys()

    with Session(auth_api["engine"]) as session:
        rows = session.exec(select(AuthSession)).all()
        assert len(rows) == 1
        persisted = rows[0]
        assert persisted.session_id == pair["session_id"]
        assert persisted.user_id == auth_api["ids"]["admin"]
        assert persisted.current_refresh_jti_digest not in {pair["refresh_token"], refresh["jti"]}
        assert len(persisted.current_refresh_jti_digest) == 64
        assert pair["access_token"] not in repr(persisted)
        assert pair["refresh_token"] not in repr(persisted)


@pytest.mark.parametrize(
    ("email", "password", "expected_status"),
    [
        ("session-admin@example.com", "wrong", 400),
        ("inactive-session@example.com", "secret", 400),
    ],
)
def test_failed_or_inactive_login_creates_no_session(
    auth_api: dict[str, Any],
    email: str,
    password: str,
    expected_status: int,
) -> None:
    response = auth_api["client"].post("/auth/token", data={"username": email, "password": password})
    assert response.status_code == expected_status
    with Session(auth_api["engine"]) as session:
        assert session.exec(select(AuthSession)).all() == []


def test_access_requires_matching_active_persisted_session(auth_api: dict[str, Any]) -> None:
    pair = _login(auth_api, "session-admin@example.com")
    with Session(auth_api["engine"], expire_on_commit=False) as session:
        user = get_current_user(token=pair["access_token"], session=session)
        assert user.id == auth_api["ids"]["admin"]

        auth_session = session.get(AuthSession, pair["session_id"])
        assert auth_session is not None
        auth_session.user_id = auth_api["ids"]["member"]
        session.add(auth_session)
        session.commit()
        with pytest.raises(HTTPException) as mismatch:
            get_current_user(token=pair["access_token"], session=session)
        assert mismatch.value.status_code == 401


def test_access_rejects_missing_nonexistent_revoked_and_expired_sessions(auth_api: dict[str, Any]) -> None:
    pair = _login(auth_api, "session-admin@example.com")
    now = datetime.now(UTC)
    missing_sid = jwt.encode(
        {
            "sub": str(auth_api["ids"]["admin"]),
            "jti": str(uuid4()),
            "type": "access",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    nonexistent = create_access_token(
        {"sub": str(auth_api["ids"]["admin"])},
        session_id=str(uuid4()),
    )
    with Session(auth_api["engine"], expire_on_commit=False) as session:
        for token in (missing_sid, nonexistent):
            with pytest.raises(HTTPException) as rejected:
                get_current_user(token=token, session=session)
            assert rejected.value.detail == "Could not validate credentials"

        auth_session = session.get(AuthSession, pair["session_id"])
        assert auth_session is not None
        auth_session.revoked_at = now
        session.add(auth_session)
        session.commit()
        with pytest.raises(HTTPException):
            get_current_user(token=pair["access_token"], session=session)

        auth_session.revoked_at = None
        auth_session.expires_at = now - timedelta(seconds=1)
        session.add(auth_session)
        session.commit()
        with pytest.raises(HTTPException):
            get_current_user(token=pair["access_token"], session=session)


def test_inactive_user_and_refresh_token_remain_rejected_at_access_boundary(auth_api: dict[str, Any]) -> None:
    pair = _login(auth_api, "session-admin@example.com")
    with Session(auth_api["engine"], expire_on_commit=False) as session:
        user = session.get(User, auth_api["ids"]["admin"])
        assert user is not None
        user.is_active = False
        session.add(user)
        session.commit()
        for token in (pair["access_token"], pair["refresh_token"]):
            with pytest.raises(HTTPException) as rejected:
                get_current_user(token=token, session=session)
            assert rejected.value.status_code == 401


def test_valid_refresh_rotates_and_reuse_revokes_complete_session(auth_api: dict[str, Any]) -> None:
    initial = _login(auth_api, "session-admin@example.com")
    rotated_response = auth_api["client"].post("/auth/refresh", json={"refresh_token": initial["refresh_token"]})
    assert rotated_response.status_code == 200
    rotated = rotated_response.json()
    assert rotated["session_id"] == initial["session_id"]
    assert _decode(rotated["access_token"])["jti"] != _decode(initial["access_token"])["jti"]
    assert _decode(rotated["refresh_token"])["jti"] != _decode(initial["refresh_token"])["jti"]
    with Session(auth_api["engine"]) as session:
        persisted = session.get(AuthSession, initial["session_id"])
        assert persisted is not None
        assert persisted.rotation_counter == 1
        assert persisted.revoked_at is None

    reuse = auth_api["client"].post("/auth/refresh", json={"refresh_token": initial["refresh_token"]})
    assert reuse.status_code == 401
    assert reuse.json()["detail"] == "Could not validate credentials"
    assert auth_api["client"].post("/auth/refresh", json={"refresh_token": rotated["refresh_token"]}).status_code == 401
    assert auth_api["client"].post("/auth/logout", headers=_bearer(rotated["access_token"])).status_code == 401
    with Session(auth_api["engine"]) as session:
        persisted = session.get(AuthSession, initial["session_id"])
        assert persisted is not None
        assert persisted.revoked_at is not None
        assert persisted.revocation_reason == "refresh-reuse"


def test_refresh_rejects_revoked_expired_and_inactive_user_sessions(auth_api: dict[str, Any]) -> None:
    revoked = _login(auth_api, "session-admin@example.com")
    expired = _login(auth_api, "session-member@example.com")
    inactive = _login(auth_api, "other-admin@example.com")
    with Session(auth_api["engine"]) as session:
        revoked_row = session.get(AuthSession, revoked["session_id"])
        expired_row = session.get(AuthSession, expired["session_id"])
        inactive_user = session.get(User, auth_api["ids"]["other_admin"])
        assert revoked_row is not None and expired_row is not None and inactive_user is not None
        revoked_row.revoked_at = datetime.now(UTC)
        revoked_row.revocation_reason = "test"
        expired_row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        inactive_user.is_active = False
        session.add_all([revoked_row, expired_row, inactive_user])
        session.commit()

    for token in (revoked["refresh_token"], expired["refresh_token"], inactive["refresh_token"]):
        response = auth_api["client"].post("/auth/refresh", json={"refresh_token": token})
        assert response.status_code == 401
        assert response.json()["detail"] == "Could not validate credentials"


def test_refresh_rejects_access_malformed_wrong_signature_and_missing_session(auth_api: dict[str, Any]) -> None:
    pair = _login(auth_api, "session-admin@example.com")
    wrong_signature = jwt.encode(
        {
            "sub": str(auth_api["ids"]["admin"]),
            "sid": pair["session_id"],
            "jti": str(uuid4()),
            "type": "refresh",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        "different-secret-with-at-least-thirty-two-bytes",
        algorithm=settings.jwt_algorithm,
    )
    for token in (pair["access_token"], "not-a-jwt", wrong_signature):
        response = auth_api["client"].post("/auth/refresh", json={"refresh_token": token})
        assert response.status_code == 401
        assert response.json()["detail"] == "Could not validate credentials"

    with Session(auth_api["engine"]) as session:
        persisted = session.get(AuthSession, pair["session_id"])
        assert persisted is not None
        session.delete(persisted)
        session.commit()
    missing = auth_api["client"].post("/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert missing.status_code == 401


def test_logout_revokes_current_session_and_invalidates_both_tokens(auth_api: dict[str, Any]) -> None:
    pair = _login(auth_api, "session-admin@example.com")
    logout = auth_api["client"].post("/auth/logout", headers=_bearer(pair["access_token"]))
    assert logout.status_code == 200
    assert logout.json() == {"revoked": True}
    assert auth_api["client"].post("/auth/logout", headers=_bearer(pair["access_token"])).status_code == 401
    assert auth_api["client"].post("/auth/refresh", json={"refresh_token": pair["refresh_token"]}).status_code == 401


def test_organization_admin_revocation_is_scoped_and_idempotent(auth_api: dict[str, Any]) -> None:
    admin = _login(auth_api, "session-admin@example.com")
    member = _login(auth_api, "session-member@example.com")
    other = _login(auth_api, "other-admin@example.com")
    org_one = auth_api["org_ids"]["one"]

    forbidden = auth_api["client"].post(
        f"/auth/sessions/{admin['session_id']}/revoke",
        params={"organization_id": org_one},
        headers=_bearer(member["access_token"]),
    )
    assert forbidden.status_code == 403

    cross_tenant = auth_api["client"].post(
        f"/auth/sessions/{other['session_id']}/revoke",
        params={"organization_id": org_one},
        headers=_bearer(admin["access_token"]),
    )
    assert cross_tenant.status_code == 404

    revoked = auth_api["client"].post(
        f"/auth/sessions/{member['session_id']}/revoke",
        params={"organization_id": org_one},
        headers=_bearer(admin["access_token"]),
    )
    assert revoked.status_code == 200
    assert revoked.json() == {"session_id": member["session_id"], "revoked": True}
    duplicate = auth_api["client"].post(
        f"/auth/sessions/{member['session_id']}/revoke",
        params={"organization_id": org_one},
        headers=_bearer(admin["access_token"]),
    )
    assert duplicate.status_code == 200
    assert auth_api["client"].post("/auth/refresh", json={"refresh_token": member["refresh_token"]}).status_code == 401


def test_session_creation_rolls_back_on_commit_failure(
    auth_api: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with Session(auth_api["engine"], expire_on_commit=False) as session:
        user = session.get(User, auth_api["ids"]["admin"])
        assert user is not None

        def fail_commit() -> None:
            raise RuntimeError("commit failed")

        monkeypatch.setattr(session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="commit failed"):
            AuthSessionService(session).create_session(user)
        assert session.exec(select(AuthSession)).all() == []


def test_refresh_rotation_rolls_back_digest_and_counter_on_commit_failure(
    auth_api: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pair = _login(auth_api, "session-admin@example.com")
    with Session(auth_api["engine"], expire_on_commit=False) as session:
        before = session.get(AuthSession, pair["session_id"])
        assert before is not None
        original_digest = before.current_refresh_jti_digest

        def fail_commit() -> None:
            raise RuntimeError("rotation commit failed")

        monkeypatch.setattr(session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="rotation commit failed"):
            AuthSessionService(session).rotate_refresh_token(pair["refresh_token"])

    with Session(auth_api["engine"]) as session:
        after = session.get(AuthSession, pair["session_id"])
        assert after is not None
        assert after.current_refresh_jti_digest == original_digest
        assert after.rotation_counter == 0
        assert after.revoked_at is None


def test_two_concurrent_refresh_uses_cannot_both_succeed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'refresh-race.db'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        user = User(email="race@example.com", password_hash=get_password_hash("secret"))
        session.add(user)
        session.commit()
        session.refresh(user)
        pair = AuthSessionService(session).create_session(user)

    barrier = Barrier(2)
    original_new_pair = AuthSessionService._new_pair

    def synchronized_pair(**kwargs: Any) -> TokenPair:
        barrier.wait(timeout=10)
        return original_new_pair(**kwargs)

    monkeypatch.setattr(AuthSessionService, "_new_pair", staticmethod(synchronized_pair))

    def rotate_once() -> str:
        with Session(engine, expire_on_commit=False) as session:
            try:
                AuthSessionService(session).rotate_refresh_token(pair.refresh_token)
            except HTTPException:
                return "rejected"
            return "rotated"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: rotate_once(), range(2)))

    assert sorted(outcomes) == ["rejected", "rotated"]
    with Session(engine) as session:
        persisted = session.get(AuthSession, pair.session_id)
        assert persisted is not None
        assert persisted.revoked_at is not None
        assert persisted.revocation_reason == "refresh-reuse"
    engine.dispose()
