"""FX API tests covering authorization, provider contracts, and backfill isolation."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from typing import Any

import pytest
from apps.api import db
from apps.api import main as api_main
from apps.api.audit import AuditActor, get_current_actor
from apps.api.models.models import Membership, Organization, User
from apps.api.routers import fx as fx_router
from apps.api.security import get_current_user
from apps.api.services.plugin_loader import ProviderHandle, ProviderMetadata
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


@contextmanager
def _create_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, dict[str, Any]]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db.engine = engine
    db.connect_args = {"check_same_thread": False}
    SQLModel.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as session:
        organization = Organization(name="FX Org")
        session.add(organization)
        session.commit()
        session.refresh(organization)
        assert organization.id is not None

        admin = User(email="fx-admin@example.com", password_hash="stub", is_active=True)
        outsider = User(email="fx-outsider@example.com", password_hash="stub", is_active=True)
        session.add_all([admin, outsider])
        session.commit()
        session.refresh(admin)
        session.refresh(outsider)
        assert admin.id is not None
        assert outsider.id is not None

        session.add(
            Membership(
                user_id=admin.id,
                organization_id=organization.id,
                can_manage_fx=True,
            )
        )
        session.commit()

    selected_user = {"value": admin}
    loaded_provider_keys: list[str] = []
    service_sessions: list[Session] = []
    sync_calls: list[dict[str, object]] = []

    class StubProvider:
        name = "stub-fx"

    class SpyFXService:
        def __init__(
            self,
            session: Session,
            provider: object,
            *,
            organization_id: int | None = None,
        ) -> None:
            self.session = session
            self.provider = provider
            self.organization_id = organization_id
            service_sessions.append(session)

        def sync(self, base: str = "USD", date_: date | None = None) -> int:
            sync_calls.append(
                {
                    "base": base,
                    "date": date_,
                    "organization_id": self.organization_id,
                    "actor": get_current_actor(),
                }
            )
            return 1

    def fake_load_provider(key: str) -> ProviderHandle:
        loaded_provider_keys.append(key)
        if key == "missing-provider":
            raise ValueError("Provider 'missing-provider' is not allowed")
        capabilities = ("market",) if key == "market:wrong" else ("fx",)
        return ProviderHandle(
            instance=StubProvider(),
            metadata=ProviderMetadata(
                key=key,
                name="Stub FX",
                description=None,
                capabilities=capabilities,
            ),
        )

    monkeypatch.setattr(api_main, "init_db", lambda: None)
    monkeypatch.setattr(api_main, "start_scheduler", lambda: None)
    monkeypatch.setattr(api_main, "shutdown_scheduler", lambda: None)
    monkeypatch.setattr(fx_router, "FXService", SpyFXService)
    monkeypatch.setattr(fx_router, "load_provider", fake_load_provider)

    app = api_main.create_app()
    app.dependency_overrides[get_current_user] = lambda: selected_user["value"]
    state: dict[str, Any] = {
        "organization_id": organization.id,
        "admin": admin,
        "outsider": outsider,
        "selected_user": selected_user,
        "loaded_provider_keys": loaded_provider_keys,
        "service_sessions": service_sessions,
        "sync_calls": sync_calls,
    }
    try:
        with TestClient(app) as client:
            yield client, state
    finally:
        engine.dispose()


def test_fx_backfill_uses_isolated_sessions_and_trusted_actor(monkeypatch: pytest.MonkeyPatch) -> None:
    with _create_client(monkeypatch) as (client, state):
        response = client.post(
            "/fx/sync",
            params={
                "organization_id": state["organization_id"],
                "base": "usd",
                "provider_key": "fx:stub",
                "backfill_days": 2,
            },
        )
        assert response.status_code == 200
        assert response.json()["base"] == "USD"
        assert response.json()["backfill_days"] == 2

        sessions = state["service_sessions"]
        calls = state["sync_calls"]
        assert len(sessions) == 3
        assert sessions[0] is not sessions[1]
        assert sessions[1] is not sessions[2]
        assert sessions[0] is not sessions[2]
        assert [call["date"] is None for call in calls] == [True, False, False]

        for call in calls[1:]:
            actor = call["actor"]
            assert isinstance(actor, AuditActor)
            assert actor.user_id == state["admin"].id
            assert actor.organization_id == state["organization_id"]
            assert call["organization_id"] == state["organization_id"]


def test_fx_authorizes_before_provider_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    with _create_client(monkeypatch) as (client, state):
        state["selected_user"]["value"] = state["outsider"]
        response = client.post(
            "/fx/sync",
            params={
                "organization_id": state["organization_id"],
                "provider_key": "missing-provider",
            },
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Not authorized for this organization"
        assert state["loaded_provider_keys"] == []


def test_fx_rejects_wrong_provider_capability(monkeypatch: pytest.MonkeyPatch) -> None:
    with _create_client(monkeypatch) as (client, state):
        response = client.post(
            "/fx/sync",
            params={
                "organization_id": state["organization_id"],
                "provider_key": "market:wrong",
            },
        )
        assert response.status_code == 400
        assert response.json()["detail"] == "Provider 'market:wrong' does not support FX synchronization"
        assert state["service_sessions"] == []


def test_fx_query_boundaries_fail_before_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    with _create_client(monkeypatch) as (client, state):
        invalid_requests = [
            {"organization_id": 0},
            {"organization_id": state["organization_id"], "backfill_days": 32},
            {"organization_id": state["organization_id"], "backfill_days": -1},
            {"organization_id": state["organization_id"], "base": "US1"},
        ]
        for params in invalid_requests:
            response = client.post("/fx/sync", params=params)
            assert response.status_code == 422

        assert state["loaded_provider_keys"] == []
        assert state["service_sessions"] == []
