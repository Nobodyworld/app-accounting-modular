"""Authentication routes for issuing JWT access tokens."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from threading import Lock
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session

from ..db import get_session
from ..security import authenticate_user, create_access_token, create_refresh_token

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


@router.post("/token")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    """Exchange username/password credentials for a bearer token."""

    identifier = _normalize_identifier(form_data.username)
    now = datetime.now(UTC)

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
    session_id = str(uuid4())
    access_token = create_access_token({"sub": str(user.id), "sid": session_id})
    refresh_token = create_refresh_token(user.id, session_id=session_id)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "session_id": session_id,
        "token_type": "bearer",
    }
