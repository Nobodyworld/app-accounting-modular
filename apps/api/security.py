"""Security primitives for OAuth2 password and JWT authentication."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, cast
from uuid import uuid4

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlmodel import Session, select

from .audit import AuditAction, AuditActor, AuditLogger, use_actor
from .config import settings
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

    return cast(bool, pwd_context.verify(plain_password, hashed_password))


def get_password_hash(password: str) -> str:
    """Return a salted hash for ``password`` using the configured scheme."""

    return cast(str, pwd_context.hash(password))


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
    expire = datetime.now(timezone.utc) + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    # TODO - Issue refresh tokens to allow long-lived sessions with rotation.
    token = jwt.encode(
        to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )
    return cast(str, token)


def _decode_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        return cast(dict[str, Any], payload)
    except JWTError as exc:  # pragma: no cover - library raises numerous subclasses
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
    # TODO - Cache organization membership lookups for high-traffic permission checks.
    return OrganizationContext(organization=organization, membership=membership)
