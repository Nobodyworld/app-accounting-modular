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

from .audit import AuditAction, AuditActor, AuditLogger, use_actor
from .config import MAX_ACCESS_TOKEN_MINUTES, settings
from .db import get_session
from .models.models import Membership, Organization, User

__all__ = [
    "OrganizationContext",
    "authenticate_user",
    "create_access_token",
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


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Create a signed JWT access token embedding ``data``."""

    to_encode = data.copy()
    to_encode.setdefault("sid", str(uuid4()))
    to_encode["type"] = "access"
    expire = datetime.now(UTC) + (
        expires_delta if expires_delta is not None else timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token


def create_refresh_token(sub: int, *, expiry_minutes: int | None = None, session_id: str | None = None) -> str:
    """Create a long-lived refresh token with rotation-friendly claims."""

    ttl = expiry_minutes or min(settings.access_token_expire_minutes * 24, MAX_ACCESS_TOKEN_MINUTES)
    expire = datetime.now(UTC) + timedelta(minutes=ttl)
    payload = {"sub": str(sub), "type": "refresh", "sid": session_id or str(uuid4()), "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _decode_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return payload
    except InvalidTokenError as exc:  # pragma: no cover - library raises numerous subclasses
        logger.warning("Failed to decode access token", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Session = Depends(get_session),
) -> User:
    """Resolve the current user from the Authorization bearer token."""

    payload = _decode_token(token)
    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_id = int(sub)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


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

    return OrganizationContext(organization=org, membership=membership)
