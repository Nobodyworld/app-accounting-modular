"""Security tests for authenticated audit actor provenance."""

from __future__ import annotations

from typing import Any

import pytest
from apps.api.audit import AuditActor, get_current_actor, use_actor
from apps.api.dependencies import authenticated_audit_context
from apps.api.models.models import Membership, Organization, User
from apps.api.security import get_current_organization, get_current_user
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient


class _MembershipResult:
    def __init__(self, membership: Membership | None) -> None:
        self.membership = membership

    def one_or_none(self) -> Membership | None:
        return self.membership


class _OrganizationSession:
    def __init__(self, organization: Organization, membership: Membership | None) -> None:
        self.organization = organization
        self.membership = membership

    def get(self, model: object, identifier: int) -> Organization | None:
        if model is Organization and identifier == self.organization.id:
            return self.organization
        return None

    def exec(self, statement: object) -> _MembershipResult:
        del statement
        return _MembershipResult(self.membership)


def _protected_app(user: User) -> FastAPI:
    app = FastAPI()

    @app.get("/protected", dependencies=[Depends(authenticated_audit_context)])
    def protected() -> dict[str, Any]:
        actor = get_current_actor()
        assert actor is not None
        return {
            "request_id": actor.request_id,
            "user_id": actor.user_id,
            "organization_id": actor.organization_id,
            "user_label": actor.user_label,
            "source": actor.source,
        }

    app.dependency_overrides[get_current_user] = lambda: user
    return app


def test_protected_route_derives_actor_from_authenticated_user() -> None:
    user = User(id=7, email="actual@example.com", password_hash="stub")

    with TestClient(_protected_app(user)) as client:
        response = client.get("/protected", headers={"X-Request-Id": "request-123"})

    assert response.status_code == 200
    assert response.json() == {
        "request_id": "request-123",
        "user_id": 7,
        "organization_id": None,
        "user_label": "actual@example.com",
        "source": "api",
    }


def test_protected_route_rejects_client_supplied_audit_identity() -> None:
    user = User(id=7, email="actual@example.com", password_hash="stub")

    with TestClient(_protected_app(user)) as client:
        response = client.get(
            "/protected",
            headers={
                "X-User-Id": "999",
                "X-Org-Id": "888",
                "X-User-Label": "forged@example.com",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Client-supplied audit identity headers are not allowed"


def test_malformed_request_id_is_not_persisted_as_actor_identity() -> None:
    user = User(id=7, email="actual@example.com", password_hash="stub")

    with TestClient(_protected_app(user)) as client:
        response = client.get("/protected", headers={"X-Request-Id": "contains spaces and control\tdata"})

    assert response.status_code == 200
    assert response.json()["request_id"] != "contains spaces and control\tdata"
    assert len(response.json()["request_id"]) == 36


def test_authorized_organization_binds_actor_after_membership_check() -> None:
    user = User(id=7, email="actual@example.com", password_hash="stub")
    organization = Organization(id=12, name="Authorized Org")
    membership = Membership(user_id=7, organization_id=12, is_admin=True)
    session = _OrganizationSession(organization, membership)
    actor = AuditActor(request_id="request-123", user_id=7, user_label=user.email, source="api")

    with use_actor(actor):
        context = get_current_organization(12, session=session, current_user=user)  # type: ignore[arg-type]

    assert context.organization.id == 12
    assert actor.user_id == 7
    assert actor.user_label == "actual@example.com"
    assert actor.organization_id == 12


def test_denied_organization_does_not_bind_actor() -> None:
    user = User(id=7, email="actual@example.com", password_hash="stub")
    organization = Organization(id=12, name="Denied Org")
    session = _OrganizationSession(organization, None)
    actor = AuditActor(request_id="request-123", user_id=7, user_label=user.email, source="api")

    with use_actor(actor), pytest.raises(HTTPException) as exc_info:
        get_current_organization(12, session=session, current_user=user)  # type: ignore[arg-type]

    assert exc_info.value.status_code == 403
    assert actor.organization_id is None
