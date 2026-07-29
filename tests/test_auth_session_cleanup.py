"""Expired authentication-session cleanup and scheduler registration tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from apps.api import scheduler
from apps.api.models.models import AuthSession, User
from apps.api.security import get_password_hash
from apps.api.services.auth_session_service import AuthSessionService, refresh_jti_digest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select


@pytest.fixture()
def cleanup_engine() -> Any:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


def _seed_sessions(engine: Any, now: datetime) -> int:
    with Session(engine, expire_on_commit=False) as session:
        user = User(email="cleanup@example.com", password_hash=get_password_hash("secret"))
        session.add(user)
        session.commit()
        session.refresh(user)
        assert user.id is not None
        session.add_all(
            [
                AuthSession(
                    session_id="expired-active",
                    user_id=user.id,
                    current_refresh_jti_digest=refresh_jti_digest("one"),
                    expires_at=now - timedelta(seconds=1),
                    created_at=now - timedelta(days=2),
                    last_rotated_at=now - timedelta(days=2),
                ),
                AuthSession(
                    session_id="expired-revoked",
                    user_id=user.id,
                    current_refresh_jti_digest=refresh_jti_digest("two"),
                    expires_at=now - timedelta(minutes=1),
                    created_at=now - timedelta(days=2),
                    last_rotated_at=now - timedelta(days=2),
                    revoked_at=now - timedelta(days=1),
                    revocation_reason="logout",
                ),
                AuthSession(
                    session_id="active",
                    user_id=user.id,
                    current_refresh_jti_digest=refresh_jti_digest("three"),
                    expires_at=now + timedelta(days=1),
                    created_at=now,
                    last_rotated_at=now,
                ),
                AuthSession(
                    session_id="active-revoked",
                    user_id=user.id,
                    current_refresh_jti_digest=refresh_jti_digest("four"),
                    expires_at=now + timedelta(days=1),
                    created_at=now,
                    last_rotated_at=now,
                    revoked_at=now,
                    revocation_reason="logout",
                ),
            ]
        )
        session.commit()
        return user.id


def test_cleanup_deletes_only_expired_sessions_and_commits(cleanup_engine: Any) -> None:
    now = datetime.now(UTC)
    user_id = _seed_sessions(cleanup_engine, now)
    with Session(cleanup_engine) as session:
        deleted = AuthSessionService(session).cleanup_expired(now=now)
    assert deleted == 2

    with Session(cleanup_engine) as session:
        assert {row.session_id for row in session.exec(select(AuthSession)).all()} == {
            "active",
            "active-revoked",
        }
        assert session.get(User, user_id) is not None


def test_cleanup_limit_is_deterministic(cleanup_engine: Any) -> None:
    now = datetime.now(UTC)
    _seed_sessions(cleanup_engine, now)
    with Session(cleanup_engine) as session:
        assert AuthSessionService(session).cleanup_expired(now=now, limit=1) == 1
    with Session(cleanup_engine) as session:
        remaining = {row.session_id for row in session.exec(select(AuthSession)).all()}
    assert "expired-active" in remaining
    assert "expired-revoked" not in remaining


def test_cleanup_rolls_back_when_commit_fails(
    cleanup_engine: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    _seed_sessions(cleanup_engine, now)
    with Session(cleanup_engine) as session:

        def fail_commit() -> None:
            raise RuntimeError("cleanup commit failed")

        monkeypatch.setattr(session, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="cleanup commit failed"):
            AuthSessionService(session).cleanup_expired(now=now)
        assert len(session.exec(select(AuthSession)).all()) == 4


def test_scheduler_registers_cleanup_job_exactly_once(monkeypatch: pytest.MonkeyPatch) -> None:
    class CapturingScheduler:
        def __init__(self) -> None:
            self.running = False
            self.job_ids: list[str] = []

        def add_job(self, *_args: object, **kwargs: object) -> None:
            self.job_ids.append(str(kwargs["id"]))

        def start(self) -> None:
            self.running = True

        def shutdown(self, *, wait: bool) -> None:
            self.running = False

        def get_jobs(self) -> list[object]:
            return []

    fake = CapturingScheduler()
    monkeypatch.setattr(scheduler, "_scheduler", None)
    monkeypatch.setattr(scheduler, "BackgroundScheduler", lambda daemon: fake)
    scheduler.start_scheduler()
    scheduler.start_scheduler()
    assert fake.job_ids.count("auth-session-cleanup") == 1
    assert fake.job_ids.count("report-refresh") == 1
    scheduler.shutdown_scheduler()


def test_scheduled_cleanup_logs_and_contains_failures(monkeypatch: pytest.MonkeyPatch, caplog: Any) -> None:
    class FailingService:
        def __init__(self, session: Session):
            self.session = session

        def cleanup_expired(self) -> int:
            raise RuntimeError("cleanup failed")

    class SessionContext:
        def __enter__(self) -> object:
            return object()

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(scheduler, "AuthSessionService", FailingService)
    monkeypatch.setattr(scheduler, "_session_scope", lambda: SessionContext())
    with caplog.at_level("ERROR"):
        scheduler._run_auth_session_cleanup()
    assert any(record.message == "Scheduled authentication-session cleanup failed" for record in caplog.records)
