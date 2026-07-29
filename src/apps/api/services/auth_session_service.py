"""Persisted authentication-session lifecycle and refresh rotation."""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import delete, update
from sqlmodel import Session, select

from ..audit import AuditAction, get_current_actor
from ..config import MAX_ACCESS_TOKEN_MINUTES, settings
from ..models.models import AuditLog, AuthSession, User
from ..security import (
    _credentials_exception,
    _decode_token,
    create_access_token,
    create_refresh_token,
)

REFRESH_SESSION_MINUTES = min(settings.access_token_expire_minutes * 24, MAX_ACCESS_TOKEN_MINUTES)
DEFAULT_CLEANUP_LIMIT = 100
MAX_CLEANUP_LIMIT = 500
MAX_REVOCATION_REASON_LENGTH = 64

logger = logging.getLogger(__name__)
_AUTH_SESSION_COLUMNS = cast(Any, AuthSession).__table__.c


@dataclass(frozen=True, slots=True)
class TokenPair:
    """A newly issued access/refresh pair sharing one persisted session."""

    access_token: str
    refresh_token: str
    session_id: str
    token_type: str = "bearer"


def refresh_jti_digest(jti: str) -> str:
    """Return the one-way digest persisted for a refresh-token identifier."""

    return hashlib.sha256(jti.encode("utf-8")).hexdigest()


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _bounded_reason(reason: str) -> str:
    return reason.strip()[:MAX_REVOCATION_REASON_LENGTH] or "revoked"


class AuthSessionService:
    """Own authentication-session persistence, rotation, revocation, and cleanup."""

    def __init__(self, session: Session):
        self.session = session

    def _stage_audit(
        self,
        *,
        event: str,
        session_id: str,
        user_id: int,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        actor = get_current_actor()
        context = {"event": event}
        if metadata:
            context.update(metadata)
        self.session.add(
            AuditLog(
                ts=datetime.now(UTC),
                action=AuditAction.ACCESS,
                entity_name=f"auth.session.{event}",
                entity_id=session_id,
                before_state=None,
                after_state={"event": event},
                payload_diff=None,
                request_id=actor.request_id if actor else str(uuid4()),
                actor_user_id=actor.user_id if actor else user_id,
                actor_org_id=actor.organization_id if actor else None,
                actor_label=actor.user_label if actor else None,
                source=actor.source if actor else "api",
                context=context,
            )
        )

    @staticmethod
    def _new_pair(
        *,
        user_id: int,
        session_id: str,
        issued_at: datetime,
        session_expires_at: datetime,
        refresh_jti: str,
    ) -> TokenPair:
        access_token = create_access_token(
            {"sub": str(user_id)},
            session_id=session_id,
            token_id=str(uuid4()),
            issued_at=issued_at,
        )
        refresh_token = create_refresh_token(
            user_id,
            session_id=session_id,
            token_id=refresh_jti,
            issued_at=issued_at,
            expires_at=session_expires_at,
        )
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            session_id=session_id,
        )

    def create_session(self, user: User, *, now: datetime | None = None) -> TokenPair:
        """Persist one session and its initial refresh digest in a single commit."""

        if user.id is None:
            raise ValueError("Persisted user id is required")
        issued_at = now or datetime.now(UTC)
        session_id = str(uuid4())
        refresh_jti = str(uuid4())
        session_expires_at = issued_at + timedelta(minutes=REFRESH_SESSION_MINUTES)
        pair = self._new_pair(
            user_id=user.id,
            session_id=session_id,
            issued_at=issued_at,
            session_expires_at=session_expires_at,
            refresh_jti=refresh_jti,
        )
        auth_session = AuthSession(
            session_id=session_id,
            user_id=user.id,
            current_refresh_jti_digest=refresh_jti_digest(refresh_jti),
            expires_at=session_expires_at,
            created_at=issued_at,
            last_rotated_at=issued_at,
        )
        try:
            self.session.add(auth_session)
            self._stage_audit(event="created", session_id=session_id, user_id=user.id)
            self.session.commit()
        except Exception:
            self.session.rollback()
            logger.exception("Failed to create authentication session", extra={"session_id": session_id})
            raise
        logger.info("Authentication session created", extra={"session_id": session_id, "user_id": user.id})
        return pair

    @staticmethod
    def _required_refresh_claims(payload: dict[str, Any]) -> tuple[int, str, str]:
        subject = payload.get("sub")
        if isinstance(subject, bool) or not isinstance(subject, (str, int)):
            raise _credentials_exception()
        try:
            user_id = int(subject)
        except (TypeError, ValueError) as exc:
            raise _credentials_exception() from exc
        sid = payload.get("sid")
        jti = payload.get("jti")
        if user_id <= 0 or not isinstance(sid, str) or not sid.strip() or not isinstance(jti, str) or not jti.strip():
            raise _credentials_exception()
        return user_id, sid.strip(), jti.strip()

    @staticmethod
    def _active(auth_session: AuthSession, now: datetime) -> bool:
        return auth_session.revoked_at is None and _utc(auth_session.expires_at) > now

    def _revoke_for_reuse(self, auth_session: AuthSession, *, now: datetime) -> None:
        result = self.session.exec(
            update(AuthSession)
            .where(
                _AUTH_SESSION_COLUMNS.session_id == auth_session.session_id,
                _AUTH_SESSION_COLUMNS.revoked_at.is_(None),
                _AUTH_SESSION_COLUMNS.expires_at > now,
            )
            .values(revoked_at=now, revocation_reason="refresh-reuse")
            .execution_options(synchronize_session=False)
        )
        if result.rowcount:
            self._stage_audit(
                event="refresh-reuse",
                session_id=auth_session.session_id,
                user_id=auth_session.user_id,
            )
        self.session.commit()
        logger.warning(
            "Refresh-token reuse revoked authentication session",
            extra={"session_id": auth_session.session_id, "user_id": auth_session.user_id},
        )

    def rotate_refresh_token(self, token: str, *, now: datetime | None = None) -> TokenPair:
        """Consume one refresh token exactly once and rotate its persisted digest."""

        payload = _decode_token(token, expected_type="refresh")
        user_id, session_id, submitted_jti = self._required_refresh_claims(payload)
        rotated_at = now or datetime.now(UTC)
        auth_session = self.session.get(AuthSession, session_id)
        if auth_session is None or auth_session.user_id != user_id or not self._active(auth_session, rotated_at):
            raise _credentials_exception()
        user = self.session.get(User, user_id)
        if user is None or not user.is_active:
            raise _credentials_exception()

        submitted_digest = refresh_jti_digest(submitted_jti)
        if not hmac.compare_digest(submitted_digest, auth_session.current_refresh_jti_digest):
            try:
                self._revoke_for_reuse(auth_session, now=rotated_at)
            except Exception:
                self.session.rollback()
                logger.exception(
                    "Failed to persist refresh-token reuse revocation",
                    extra={"session_id": session_id, "user_id": user_id},
                )
                raise
            raise _credentials_exception()

        new_refresh_jti = str(uuid4())
        pair = self._new_pair(
            user_id=user_id,
            session_id=session_id,
            issued_at=rotated_at,
            session_expires_at=_utc(auth_session.expires_at),
            refresh_jti=new_refresh_jti,
        )
        try:
            result = self.session.exec(
                update(AuthSession)
                .where(
                    _AUTH_SESSION_COLUMNS.session_id == session_id,
                    _AUTH_SESSION_COLUMNS.current_refresh_jti_digest == submitted_digest,
                    _AUTH_SESSION_COLUMNS.revoked_at.is_(None),
                    _AUTH_SESSION_COLUMNS.expires_at > rotated_at,
                )
                .values(
                    current_refresh_jti_digest=refresh_jti_digest(new_refresh_jti),
                    last_rotated_at=rotated_at,
                    rotation_counter=_AUTH_SESSION_COLUMNS.rotation_counter + 1,
                )
                .execution_options(synchronize_session=False)
            )
            if result.rowcount == 1:
                self._stage_audit(event="refreshed", session_id=session_id, user_id=user_id)
                self.session.commit()
                logger.info(
                    "Authentication session refresh rotated",
                    extra={"session_id": session_id, "user_id": user_id},
                )
                return pair

            self.session.rollback()
            self.session.expire_all()
            current = self.session.get(AuthSession, session_id)
            if current is not None and current.user_id == user_id and self._active(current, rotated_at):
                self._revoke_for_reuse(current, now=rotated_at)
            raise _credentials_exception()
        except Exception:
            self.session.rollback()
            raise

    def revoke_session(
        self,
        session_id: str,
        *,
        reason: str,
        event: str,
        now: datetime | None = None,
    ) -> bool:
        """Idempotently revoke a single session, returning whether it changed."""

        revoked_at = now or datetime.now(UTC)
        auth_session = self.session.get(AuthSession, session_id)
        if auth_session is None:
            return False
        try:
            result = self.session.exec(
                update(AuthSession)
                .where(
                    _AUTH_SESSION_COLUMNS.session_id == session_id,
                    _AUTH_SESSION_COLUMNS.revoked_at.is_(None),
                )
                .values(revoked_at=revoked_at, revocation_reason=_bounded_reason(reason))
                .execution_options(synchronize_session=False)
            )
            changed = result.rowcount == 1
            if changed:
                self._stage_audit(
                    event=event,
                    session_id=session_id,
                    user_id=auth_session.user_id,
                )
            self.session.commit()
        except Exception:
            self.session.rollback()
            logger.exception(
                "Failed to revoke authentication session",
                extra={"session_id": session_id, "event": event},
            )
            raise
        logger.info(
            "Authentication session revocation processed",
            extra={"session_id": session_id, "user_id": auth_session.user_id, "event": event, "changed": changed},
        )
        return changed

    def cleanup_expired(
        self,
        *,
        now: datetime | None = None,
        limit: int = DEFAULT_CLEANUP_LIMIT,
    ) -> int:
        """Delete at most ``limit`` sessions after their refresh expiration."""

        cleanup_at = now or datetime.now(UTC)
        bounded_limit = max(1, min(limit, MAX_CLEANUP_LIMIT))
        try:
            session_ids = list(
                self.session.exec(
                    select(AuthSession.session_id)
                    .where(AuthSession.expires_at <= cleanup_at)
                    .order_by(_AUTH_SESSION_COLUMNS.expires_at, _AUTH_SESSION_COLUMNS.session_id)
                    .limit(bounded_limit)
                ).all()
            )
            if not session_ids:
                return 0
            result = self.session.exec(delete(AuthSession).where(_AUTH_SESSION_COLUMNS.session_id.in_(session_ids)))
            deleted = int(result.rowcount or 0)
            self.session.commit()
        except Exception:
            self.session.rollback()
            logger.exception("Failed to clean up expired authentication sessions")
            raise
        logger.info("Expired authentication sessions cleaned up", extra={"deleted": deleted})
        return deleted

    def opportunistic_cleanup(self) -> int:
        """Run bounded cleanup without making login or refresh availability depend on it."""

        try:
            return self.cleanup_expired(limit=DEFAULT_CLEANUP_LIMIT)
        except Exception:
            return 0
