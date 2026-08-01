"""Regression coverage for JWT access and refresh token separation."""

from __future__ import annotations

import pytest
from apps.api.models.models import User
from apps.api.security import (
    _decode_token,
    create_access_token,
    create_refresh_token,
    get_current_user,
    get_password_hash,
)
from apps.api.services.auth_session_service import AuthSessionService
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture()
def persisted_user_session():
    """Create an isolated persisted user for direct dependency testing."""

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        user = User(
            email="token-boundary@example.com",
            password_hash=get_password_hash("nonproduction-secret"),
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        assert user.id is not None
        pair = AuthSessionService(session).create_session(user)
        yield session, user, pair
    engine.dispose()


def test_access_token_resolves_current_user(persisted_user_session) -> None:
    session, user, pair = persisted_user_session
    token = pair.access_token

    resolved = get_current_user(token=token, session=session)

    assert resolved.id == user.id


def test_refresh_token_is_rejected_by_access_boundary(persisted_user_session) -> None:
    session, user, _ = persisted_user_session
    token = create_refresh_token(user.id)

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(token=token, session=session)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Could not validate credentials"


def test_access_token_is_rejected_by_refresh_validation(persisted_user_session) -> None:
    _, user, _ = persisted_user_session
    token = create_access_token({"sub": str(user.id)})

    with pytest.raises(HTTPException) as exc_info:
        _decode_token(token, expected_type="refresh")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Could not validate credentials"


def test_refresh_token_passes_refresh_validation(persisted_user_session) -> None:
    _, user, _ = persisted_user_session
    token = create_refresh_token(user.id)

    payload = _decode_token(token, expected_type="refresh")

    assert payload["sub"] == str(user.id)
    assert payload["type"] == "refresh"
