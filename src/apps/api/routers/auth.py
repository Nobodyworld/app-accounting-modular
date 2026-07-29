"""Authentication routes for issuing JWT access tokens."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select

from ..db import get_session
from ..models.models import AuthSession, Membership
from ..schemas import (
    AdminSessionRevocationResponse,
    LoginTokenResponse,
    LogoutResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
)
from ..security import (
    AuthenticationContext,
    OrganizationContext,
    authenticate_user,
    get_authentication_context,
    get_current_organization,
)
from ..services.auth_session_service import AuthSessionService

router = APIRouter(prefix="/auth", tags=["auth"])

_failed_attempts: defaultdict[str, deque[datetime]] = defaultdict(deque)
_lockouts: dict[str, datetime] = {}
_lock = Lock()
_MAX_ATTEMPTS = 5
_WINDOW = timedelta(minutes=2)
_LOCKOUT_DURATION = timedelta(minutes=5)


def _normalize_identifier(username: str) -> str:
    return username.strip().lower()


def _prune_attempts(identifier: str, now: datetime) -> None:
    attempts = _failed_attempts[identifier]
    while attempts and now - attempts[0] > _WINDOW:
        attempts.popleft()
    if not attempts:
        _failed_attempts.pop(identifier, None)


def _register_failure(identifier: str, now: datetime) -> None:
    attempts = _failed_attempts[identifier]
    attempts.append(now)
    if len(attempts) >= _MAX_ATTEMPTS:
        _lockouts[identifier] = now + _LOCKOUT_DURATION
        attempts.clear()


def _clear_failures(identifier: str) -> None:
    _failed_attempts.pop(identifier, None)
    _lockouts.pop(identifier, None)


@router.post("/token", response_model=LoginTokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
) -> LoginTokenResponse:
    """Exchange username/password credentials for a bearer token."""

    identifier = _normalize_identifier(form_data.username)
    now = datetime.now(UTC)
    service = AuthSessionService(session)
    service.opportunistic_cleanup()

    with _lock:
        locked_until = _lockouts.get(identifier)
        if locked_until is not None and locked_until > now:
            raise HTTPException(
                status_code=429,
                detail="Too many failed attempts. Try again later.",
            )
        _prune_attempts(identifier, now)

    user = authenticate_user(session, identifier, form_data.password)
    if user is None:
        with _lock:
            _register_failure(identifier, now)
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    with _lock:
        _clear_failures(identifier)
    if user.id is None:  # pragma: no cover - persisted users should always have an id
        raise HTTPException(status_code=500, detail="Authenticated user is missing an id")
    pair = service.create_session(user, now=now)
    return LoginTokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        session_id=pair.session_id,
    )


@router.post("/refresh", response_model=RefreshTokenResponse)
def refresh(
    request: RefreshTokenRequest,
    session: Session = Depends(get_session),
) -> RefreshTokenResponse:
    """Consume a refresh token once and return its rotated pair."""

    service = AuthSessionService(session)
    service.opportunistic_cleanup()
    pair = service.rotate_refresh_token(request.refresh_token)
    return RefreshTokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        session_id=pair.session_id,
    )


@router.post("/logout", response_model=LogoutResponse)
def logout(
    context: AuthenticationContext = Depends(get_authentication_context),
    session: Session = Depends(get_session),
) -> LogoutResponse:
    """Revoke the currently authenticated access-token session."""

    service = AuthSessionService(session)
    service.revoke_session(
        context.auth_session.session_id,
        reason="logout",
        event="logout",
    )
    return LogoutResponse(revoked=True)


@router.post("/sessions/{session_id}/revoke", response_model=AdminSessionRevocationResponse)
def revoke_organization_session(
    session_id: Annotated[str, Path(min_length=1, max_length=64)],
    organization_context: OrganizationContext = Depends(get_current_organization),
    session: Session = Depends(get_session),
) -> AdminSessionRevocationResponse:
    """Allow an organization administrator to revoke a member's session."""

    if not organization_context.membership.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )

    target_session = session.get(AuthSession, session_id)
    if target_session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    target_membership = session.exec(
        select(Membership).where(
            Membership.user_id == target_session.user_id,
            Membership.organization_id == organization_context.organization.id,
        )
    ).one_or_none()
    if target_membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    AuthSessionService(session).revoke_session(
        session_id,
        reason="organization-admin",
        event="admin-revoked",
    )
    return AdminSessionRevocationResponse(session_id=session_id, revoked=True)
