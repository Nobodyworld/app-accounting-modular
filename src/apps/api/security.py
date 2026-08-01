"""Security primitives for OAuth2 password and JWT authentication."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Annotated, Any
from uuid import uuid4

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from passlib.context import CryptContext
from sqlmodel import Session, select

from .audit import AuditAction, AuditActor, AuditLogger, get_current_actor, use_actor
from .config import MAX_ACCESS_TOKEN_MINUTES, settings
from .db import get_session
from .models.models import AuthSession, Membership, Organization, User

__all__ = [
    "AuthenticationContext",
    "OrganizationContext",
    "authenticate_user",
    "create_access_token",
    "create_refresh_token",
    "get_authentication_context",
    "get_current_organization",
    "get_current_user",
    "get_password_hash",
    "oauth2_scheme",
    "verify_password",
]

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")
logger = logging.getLogger(__name__)


def _record_auth_attempt(
    session: Session,
    *,
    email: str,
    success: bool,
    reason: str | None = None,
    user: User | None = None,
) -> None:
    """Persist an audit log entry describing an authentication attempt."""

    metadata: dict[str, Any] = {"email": email, "success": success}
    if reason is not None:
        metadata["reason"] = reason

    actor = AuditActor(
        request_id=str(uuid4()),
        user_id=user.id if success and user is not None else None,
        user_label=(user.email if user is not None else email),
    )

    audit_logger = AuditLogger(session)
    with use_actor(actor):
        audit_logger.log(
            action=AuditAction.ACCESS,
            entity_name="auth.login",
            entity_id=str(user.id if user is not None else email),
            before=None,
            after={"success": success},
            metadata=metadata,
        )

    log_method = logger.info if success else logger.warning
    log_method(
        "Authentication attempt",
        extra={
            "email": email,
            "success": success,
            "reason": reason,
            "user_id": getattr(user, "id", None),
        },
    )


@dataclass(slots=True)
class OrganizationContext:
    """Container pairing an organization with the member's permissions."""

    organization: Organization
    membership: Membership


@dataclass(slots=True)
class AuthenticationContext:
    """Validated access-token identity and its active persisted session."""

    user: User
    auth_session: AuthSession
    claims: dict[str, Any]


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return ``True`` if ``plain_password`` matches ``hashed_password``."""

    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Return a salted hash for ``password`` using the configured scheme."""

    return pwd_context.hash(password)


def authenticate_user(session: Session, email: str, password: str) -> User | None:
    """Return the matching :class:`User` if the credentials validate."""

    stmt = select(User).where(User.email == email)
    user = session.exec(stmt).one_or_none()
    if user is None or not user.is_active:
        _record_auth_attempt(
            session,
            email=email,
            success=False,
            reason="inactive-or-missing",
            user=user,
        )
        return None
    if not verify_password(password, user.password_hash):
        _record_auth_attempt(
            session,
            email=email,
            success=False,
            reason="invalid-password",
            user=user,
        )
        return None
    _record_auth_attempt(session, email=email, success=True, user=user)
    return user


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
    *,
    session_id: str | None = None,
    token_id: str | None = None,
    issued_at: datetime | None = None,
) -> str:
    """Create a signed access JWT containing only the required non-sensitive claims."""

    now = issued_at or datetime.now(UTC)
    subject = str(data.get("sub", "")).strip()
    sid = str(session_id or data.get("sid") or uuid4()).strip()
    payload = {
        "sub": subject,
        "sid": sid,
        "jti": token_id or str(uuid4()),
        "type": "access",
        "iat": now,
        "exp": now
        + (expires_delta if expires_delta is not None else timedelta(minutes=settings.access_token_expire_minutes)),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(
    sub: int,
    *,
    expiry_minutes: int | None = None,
    session_id: str | None = None,
    token_id: str | None = None,
    issued_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> str:
    """Create a signed refresh JWT containing rotation-safe identifiers."""

    now = issued_at or datetime.now(UTC)
    ttl = expiry_minutes or min(settings.access_token_expire_minutes * 24, MAX_ACCESS_TOKEN_MINUTES)
    expire = expires_at or now + timedelta(minutes=ttl)
    payload = {
        "sub": str(sub),
        "sid": session_id or str(uuid4()),
        "jti": token_id or str(uuid4()),
        "type": "refresh",
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _credentials_exception() -> HTTPException:
    """Return a fresh generic bearer-credential rejection."""

    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _decode_token(token: str, *, expected_type: str) -> dict[str, Any]:
    """Decode a JWT and require its declared token type."""

    try:
        decoded = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        if not isinstance(decoded, dict):
            raise InvalidTokenError("JWT payload must be an object")
        if decoded.get("type") != expected_type:
            raise InvalidTokenError(f"Expected {expected_type} token")
        return {str(key): value for key, value in decoded.items()}
    except InvalidTokenError as exc:  # pragma: no cover - library raises numerous subclasses
        logger.warning("Failed to decode %s token", expected_type, exc_info=exc)
        raise _credentials_exception() from exc


def _utc(value: datetime) -> datetime:
    """Normalize persisted timestamps, including SQLite's naive round trips."""

    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _integer_subject(payload: dict[str, Any]) -> int:
    """Return a positive integer JWT subject or reject the credential generically."""

    subject = payload.get("sub")
    if isinstance(subject, bool) or not isinstance(subject, (str, int)):
        raise _credentials_exception()
    try:
        user_id = int(subject)
    except (TypeError, ValueError) as exc:
        raise _credentials_exception() from exc
    if user_id <= 0:
        raise _credentials_exception()
    return user_id


def get_authentication_context(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Session = Depends(get_session),
) -> AuthenticationContext:
    """Validate an access token against its persisted active session and user."""

    payload = _decode_token(token, expected_type="access")
    user_id = _integer_subject(payload)
    sid = payload.get("sid")
    if not isinstance(sid, str) or not sid.strip():
        raise _credentials_exception()

    auth_session = session.get(AuthSession, sid.strip())
    now = datetime.now(UTC)
    if (
        auth_session is None
        or auth_session.user_id != user_id
        or auth_session.revoked_at is not None
        or _utc(auth_session.expires_at) <= now
    ):
        raise _credentials_exception()

    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise _credentials_exception()
    return AuthenticationContext(user=user, auth_session=auth_session, claims=payload)


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Session = Depends(get_session),
) -> User:
    """Compatibility wrapper returning the user from a validated session context."""

    return get_authentication_context(token=token, session=session).user


def _bind_audit_actor(current_user: User, organization_id: int) -> None:
    """Bind authorized tenant identity to the active request actor."""

    actor = get_current_actor()
    if actor is None:
        return
    actor.user_id = current_user.id
    actor.user_label = current_user.email
    actor.organization_id = organization_id


def get_current_organization(
    organization_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> OrganizationContext:
    """Return the organization ensuring the current user is a member."""

    organization = session.get(Organization, organization_id)
    if organization is None or not organization.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    stmt = select(Membership).where(
        Membership.organization_id == organization_id,
        Membership.user_id == current_user.id,
    )
    membership = session.exec(stmt).one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized for this organization",
        )
    _bind_audit_actor(current_user, organization_id)
    return OrganizationContext(organization=organization, membership=membership)


# Lightweight in-process cache to reduce DB round trips for membership checks within the same worker.
@lru_cache(maxsize=1024)
def _membership_cache_key(user_id: int, organization_id: int) -> tuple[int, int]:
    return (user_id, organization_id)


_organization_context_cache: dict[tuple[int, int], tuple[int | None, Membership]] = {}


def get_current_organization_cached(
    organization_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> OrganizationContext:
    """Cached variant of ``get_current_organization`` for high-traffic checks."""

    key = _membership_cache_key(current_user.id, organization_id)
    membership: Membership | None = None
    org: Organization | None = None
    try:
        org_id, mem = _organization_context_cache[key]
        org = session.get(Organization, org_id)
        membership = mem
    except Exception:
        membership = None

    if membership is None or org is None:
        ctx = get_current_organization(organization_id, session, current_user)
        _organization_context_cache[key] = (ctx.organization.id, ctx.membership)
        return ctx

    _bind_audit_actor(current_user, organization_id)
    return OrganizationContext(organization=org, membership=membership)
