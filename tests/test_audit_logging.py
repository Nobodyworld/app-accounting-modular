"""Audit logging integration tests across domain service boundaries."""

from __future__ import annotations

import types
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from threading import Barrier
from typing import Any, Literal, cast

import pytest
from apps.api.audit import AuditActor, AuditLogger, use_actor
from apps.api.models.models import (
    AuditAction,
    AuditLog,
    Instrument,
    Organization,
    Price,
    Rate,
    TaxRule,
    User,
)
from apps.api.security import get_password_hash
from apps.api.services.fx_service import BaseFXProvider, FXService
from apps.api.services.ledger_service import LedgerService
from apps.api.services.market_service import BaseMarketProvider, MarketService
from apps.api.services.tax_service import BaseTaxProvider, TaxService
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select


@contextmanager
def _create_session() -> Iterator[Session]:
    """Initialise an isolated in-memory database session for audit tests."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed_actor(session: Session) -> AuditActor:
    """Create and persist an organisation/user pair for audit context."""
    org = Organization(name="Test Org")
    session.add(org)
    session.commit()
    session.refresh(org)

    user = User(
        email="test@example.com",
        name="Tester",
        organization_id=org.id,
        password_hash=get_password_hash("secret"),
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    return AuditActor(
        request_id="test-request",
        user_id=user.id,
        organization_id=org.id,
        source="tests",
        user_label=user.email,
    )


class _StubFXProvider:
    name = "stubfx"

    def sync_daily_rates(self, base: str = "USD", date_: date | None = None) -> list[Rate]:
        return [Rate(base=base, quote="EUR", date=date(2024, 1, 1), value=1.1, provider=self.name)]


class _StubMarketProvider:
    name = "stubmarket"

    def fetch_prices(self, symbol: str, start: date, end: date) -> list[Price]:
        return [Price(instrument_id=0, date=start, close=101.5, provider=self.name)]


class _StubTaxProvider:
    name = "stubtax"

    def upsert_rules(self) -> list[TaxRule]:
        return [TaxRule(jurisdiction="US-FED", scope="vat", expression="rate * 0.2")]


# TODO - (audit) Simulate concurrent writes to verify audit log race condition handling.
def test_concurrent_async_audit_logs() -> None:
    with _create_session() as session:
        logger = AuditLogger(session)
        count = 20

        def _worker(idx: int) -> None:
            logger.log(
                AuditAction.CREATE,
                "Concurrent",
                idx,
                after={"index": idx},
                asynchronous=True,
            )

        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=5) as pool:
            for i in range(count):
                pool.submit(_worker, i)

        logger.flush()
        rows = session.exec(select(AuditLog).where(AuditLog.entity_name == "Concurrent")).all()
        assert len(rows) == count


def test_async_audit_worker_single_initialization_under_concurrency() -> None:
    with _create_session() as session:
        logger = AuditLogger(session)
        original_worker_loop = logger._worker_loop
        worker_starts = 0

        def _wrapped_worker_loop(self: AuditLogger) -> None:
            nonlocal worker_starts
            worker_starts += 1
            original_worker_loop()

        logger._worker_loop = types.MethodType(_wrapped_worker_loop, logger)

        submissions = 60
        concurrency = 12
        barrier = Barrier(concurrency)

        def _worker(idx: int) -> None:
            barrier.wait()
            logger.log(
                AuditAction.CREATE,
                "ConcurrentInit",
                idx,
                after={"index": idx},
                asynchronous=True,
            )

        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            for i in range(submissions):
                pool.submit(_worker, i)

        logger.flush()
        rows = session.exec(select(AuditLog).where(AuditLog.entity_name == "ConcurrentInit")).all()
        persisted_ids = {row.entity_id for row in rows}

        assert worker_starts == 1
        assert logger._worker is not None
        assert len(rows) == submissions
        assert len(persisted_ids) == submissions

        logger.close()
        assert logger._worker is not None
        assert not logger._worker.is_alive()


def test_ledger_post_transaction_creates_audit_entry() -> None:
    with _create_session() as session:
        actor = _seed_actor(session)
        with use_actor(actor):
            ledger = LedgerService(session)
            cash = ledger.create_account(name="Cash", type="ASSET", code="1000")
            revenue = ledger.create_account(name="Revenue", type="REVENUE", code="4000")
            ledger.post_transaction(
                date=date(2024, 1, 1),
                description="Sale",
                postings=[
                    {"account_id": cash.id, "debit": 150.0, "credit": 0.0},
                    {"account_id": revenue.id, "debit": 0.0, "credit": 150.0},
                ],
            )

        stmt = select(AuditLog).where(AuditLog.entity_name == "Transaction").order_by(cast(Any, AuditLog.ts).desc())
        log = session.exec(stmt).first()
        assert log is not None
        assert log.action == AuditAction.CREATE
        assert log.actor_user_id == actor.user_id
        assert log.after_state is not None
        assert log.after_state["description"] == "Sale"


def test_fx_sync_produces_audit_entry() -> None:
    with _create_session() as session:
        actor = _seed_actor(session)
        provider = _StubFXProvider()
        with use_actor(actor):
            svc = FXService(session, cast(BaseFXProvider, provider))
            count = svc.sync(base="USD")

        assert count == 1
        stmt = select(AuditLog).where(AuditLog.entity_name == "Rate").order_by(cast(Any, AuditLog.ts).desc())
        log = session.exec(stmt).first()
        assert log is not None
        assert log.after_state is not None
        assert log.after_state["rates"][0]["provider"] == provider.name


def test_market_sync_produces_audit_entry() -> None:
    with _create_session() as session:
        actor = _seed_actor(session)
        provider = _StubMarketProvider()
        with use_actor(actor):
            svc = MarketService(session, cast(BaseMarketProvider, provider))
            count = svc.sync_prices("TEST", date(2024, 1, 1), date(2024, 1, 1))

        assert count == 1
        stmt = select(AuditLog).where(AuditLog.entity_name == "Price").order_by(cast(Any, AuditLog.ts).desc())
        log = session.exec(stmt).first()
        assert log is not None
        assert log.after_state is not None
        assert log.after_state["provider"] == provider.name


def test_tax_sync_produces_audit_entry() -> None:
    with _create_session() as session:
        actor = _seed_actor(session)
        provider = _StubTaxProvider()
        with use_actor(actor):
            svc = TaxService(session, cast(BaseTaxProvider, provider))
            count = svc.sync_rules()

        assert count == 1
        stmt = select(AuditLog).where(AuditLog.entity_name == "TaxRule").order_by(cast(Any, AuditLog.ts).desc())
        log = session.exec(stmt).first()
        assert log is not None
        assert log.after_state is not None
        assert log.after_state["provider"] == provider.name


def test_fx_sync_rolls_back_on_commit_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    with _create_session() as session:
        provider = _StubFXProvider()
        svc = FXService(session, cast(BaseFXProvider, provider))

        original_rollback = session.rollback
        rollback_called = False

        def failing_commit() -> None:
            raise RuntimeError("boom")

        def tracking_rollback() -> None:
            nonlocal rollback_called
            rollback_called = True
            original_rollback()

        monkeypatch.setattr(session, "commit", failing_commit)
        monkeypatch.setattr(session, "rollback", tracking_rollback)

        with pytest.raises(RuntimeError):
            svc.sync(base="USD")

        assert rollback_called is True
        assert session.exec(select(Rate)).all() == []


def test_market_sync_rolls_back_on_commit_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    with _create_session() as session:
        actor = _seed_actor(session)
        provider = _StubMarketProvider()

        instrument = Instrument(symbol="TEST", name="Test", organization_id=actor.organization_id)
        session.add(instrument)
        session.commit()
        session.refresh(instrument)

        svc = MarketService(session, cast(BaseMarketProvider, provider))

        original_rollback = session.rollback
        rollback_called = False

        def failing_commit() -> None:
            raise RuntimeError("boom")

        def tracking_rollback() -> None:
            nonlocal rollback_called
            rollback_called = True
            original_rollback()

        monkeypatch.setattr(session, "commit", failing_commit)
        monkeypatch.setattr(session, "rollback", tracking_rollback)

        with pytest.raises(RuntimeError):
            svc.sync_prices("TEST", date(2024, 1, 1), date(2024, 1, 1))

        assert rollback_called is True
        assert session.exec(select(Price)).all() == []


def test_tax_sync_rolls_back_on_commit_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    with _create_session() as session:
        provider = _StubTaxProvider()
        svc = TaxService(session, cast(BaseTaxProvider, provider))

        original_rollback = session.rollback
        rollback_called = False

        def failing_commit() -> None:
            raise RuntimeError("boom")

        def tracking_rollback() -> None:
            nonlocal rollback_called
            rollback_called = True
            original_rollback()

        monkeypatch.setattr(session, "commit", failing_commit)
        monkeypatch.setattr(session, "rollback", tracking_rollback)

        with pytest.raises(RuntimeError):
            svc.sync_rules()

        assert rollback_called is True
        assert session.exec(select(TaxRule)).all() == []


def test_async_audit_logging_flushes_background_entries() -> None:
    with _create_session() as session:
        logger = AuditLogger(session)
        logger.log(
            AuditAction.CREATE,
            "Entity",
            1,
            after={"field": "value"},
            asynchronous=True,
        )
        logger.flush()
        stmt = select(AuditLog).where(AuditLog.entity_name == "Entity")
        log = session.exec(stmt).first()
        assert log is not None
        assert log.after_state == {"field": "value"}


def test_async_audit_logging_handles_flush_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    with _create_session() as session:
        logger = AuditLogger(session)

        class FailingSession:
            def __enter__(self) -> FailingSession:
                return self

            def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> Literal[False]:
                return False

            def add(self, _: object) -> None:
                return None

            def commit(self) -> None:
                raise RuntimeError("boom")

        logger.log(AuditAction.CREATE, "Entity", 1, asynchronous=True)
        logger._session_factory = cast(Any, lambda: FailingSession())
        logger.flush()
        logger.close()
