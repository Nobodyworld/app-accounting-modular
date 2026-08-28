"""Authenticated API coverage for tenant provider governance."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from apps.api import db
from apps.api.db import get_session
from apps.api.main import create_app
from apps.api.models.models import AuditLog, Membership, Organization, OrganizationProviderPolicy, User
from apps.api.security import get_password_hash
from apps.api.services.auth_session_service import AuthSessionService
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select


@pytest.fixture()
def governance_api(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, dict[str, Any]]]:
    monkeypatch.setenv("OPENEXCHANGERATES_APP_ID", "api-secret-must-not-leak")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    db.engine = engine
    SQLModel.metadata.create_all(engine)
    app = create_app()

    def override_get_session() -> Iterator[Session]:
        with Session(engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    with Session(engine, expire_on_commit=False) as session:
        first = Organization(name="Governed Organization")
        second = Organization(name="Other Organization")
        admin = User(email="governance-admin@example.test", password_hash=get_password_hash("secret"))
        member = User(email="governance-member@example.test", password_hash=get_password_hash("secret"))
        other = User(email="governance-other@example.test", password_hash=get_password_hash("secret"))
        session.add_all([first, second, admin, member, other])
        session.commit()
        for row in (first, second, admin, member, other):
            session.refresh(row)
        assert first.id is not None and second.id is not None
        assert admin.id is not None and member.id is not None and other.id is not None
        session.add_all(
            [
                Membership(organization_id=first.id, user_id=admin.id, is_admin=True),
                Membership(organization_id=first.id, user_id=member.id),
                Membership(organization_id=second.id, user_id=other.id, is_admin=True),
            ]
        )
        session.commit()
        context = {
            "org": first.id,
            "other_org": second.id,
            "admin": AuthSessionService(session).create_session(admin).access_token,
            "member": AuthSessionService(session).create_session(member).access_token,
            "other": AuthSessionService(session).create_session(other).access_token,
        }
    with TestClient(app) as client:
        yield client, context
    engine.dispose()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_catalog_is_authenticated_member_readable_and_cross_tenant_nondisclosing(governance_api) -> None:
    client, context = governance_api
    assert client.get("/providers", params={"organization_id": context["org"]}).status_code == 401

    member = client.get(
        "/providers",
        params={"organization_id": context["org"]},
        headers=_headers(context["member"]),
    )
    assert member.status_code == 200, member.text
    payload = member.json()
    assert payload["can_manage"] is False
    assert payload["providers"]
    first_provider = payload["providers"][0]
    assert first_provider["provider_version"]
    assert first_provider["sdk_version"]
    assert first_provider["compatibility"]["status"] in {"compatible", "incompatible"}
    assert payload["providers"]
    assert all("module" not in row for row in payload["providers"])

    cross_tenant = client.get(
        "/providers",
        params={"organization_id": context["org"]},
        headers=_headers(context["other"]),
    )
    assert cross_tenant.status_code == 404
    missing = client.get(
        "/providers",
        params={"organization_id": 999_999},
        headers=_headers(context["other"]),
    )
    assert missing.status_code == 404
    assert cross_tenant.json() == missing.json()


def test_member_cannot_mutate_and_tenant_cannot_submit_module_identity(governance_api) -> None:
    client, context = governance_api
    path = "/providers/fx:ecb/policy"
    member = client.put(
        path,
        params={"organization_id": context["org"]},
        headers=_headers(context["member"]),
        json={"enabled": False, "revision": 0},
    )
    assert member.status_code == 403

    for field, value in (
        ("package", "tenant-provider.whl"),
        ("wheel", "tenant-provider.whl"),
        ("url", "https://invalid.example/provider"),
        ("module", "tenant.evil.provider"),
        ("factory", "build"),
        ("entry_point", "tenant:provider"),
        ("manifest", {"key": "market:tenant"}),
    ):
        arbitrary_identity = client.put(
            path,
            params={"organization_id": context["org"]},
            headers=_headers(context["admin"]),
            json={"enabled": True, "revision": 0, field: value},
        )
        assert arbitrary_identity.status_code == 422, field
    with Session(db.engine) as session:
        assert session.exec(select(OrganizationProviderPolicy)).first() is None


def test_admin_policy_default_cas_and_atomic_audit(governance_api) -> None:
    client, context = governance_api
    headers = _headers(context["admin"])
    params = {"organization_id": context["org"]}
    created = client.put(
        "/providers/fx:ecb/policy",
        params=params,
        headers=headers,
        json={"enabled": True, "note": "Reference default", "revision": 0},
    )
    assert created.status_code == 200, created.text
    assert created.json()["revision"] == 1
    stale = client.put(
        "/providers/fx:ecb/policy",
        params=params,
        headers=headers,
        json={"enabled": False, "revision": 0},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "PROVIDER_GOVERNANCE_CONFLICT"

    selected = client.put(
        "/providers/defaults/fx",
        params=params,
        headers=headers,
        json={"provider_key": "fx:ecb", "revision": 0},
    )
    assert selected.status_code == 200, selected.text
    assert selected.json()["revision"] == 1

    unsupported = client.put(
        "/providers/defaults/not-a-capability",
        params=params,
        headers=headers,
        json={"provider_key": "fx:ecb", "revision": 0},
    )
    assert unsupported.status_code == 422
    assert unsupported.json()["detail"]["code"] == "PROVIDER_GOVERNANCE_VALIDATION"

    changed = client.put(
        "/providers/defaults/fx",
        params=params,
        headers=headers,
        json={"provider_key": "fx:openexchangerates", "revision": 1},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["revision"] == 2
    assert changed.json()["provider_key"] == "fx:openexchangerates"

    stale_clear = client.delete(
        "/providers/defaults/fx",
        params={**params, "revision": 1},
        headers=headers,
    )
    assert stale_clear.status_code == 409
    assert stale_clear.json()["detail"]["code"] == "PROVIDER_GOVERNANCE_CONFLICT"

    cleared = client.delete(
        "/providers/defaults/fx",
        params={**params, "revision": 2},
        headers=headers,
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json() == {"capability": "fx", "cleared": True, "revision": 2}

    reselected = client.put(
        "/providers/defaults/fx",
        params=params,
        headers=headers,
        json={"provider_key": "fx:ecb", "revision": 0},
    )
    assert reselected.status_code == 200, reselected.text
    disabled = client.put(
        "/providers/fx:ecb/policy",
        params=params,
        headers=headers,
        json={"enabled": False, "note": "Policy review", "revision": 1},
    )
    assert disabled.status_code == 200, disabled.text
    policies = client.get("/providers/policies", params=params, headers=headers).json()
    assert policies["defaults"][0]["effective"] is False

    with Session(db.engine) as session:
        policy = session.exec(select(OrganizationProviderPolicy)).one()
        audits = list(
            session.exec(
                select(AuditLog).where(
                    AuditLog.actor_org_id == context["org"],
                    AuditLog.entity_name.in_(["OrganizationProviderPolicy", "OrganizationCapabilityDefault"]),
                )
            )
        )
        assert policy.enabled is False
        assert policy.revision == 2
        assert len(audits) == 6
        assert policy.audit_reference == str(audits[-1].id)


def test_credential_and_evidence_outputs_are_secret_free_and_deterministic(governance_api) -> None:
    client, context = governance_api
    headers = _headers(context["member"])
    params = {"organization_id": context["org"]}
    credentials = client.get("/providers/credentials", params=params, headers=headers)
    assert credentials.status_code == 200, credentials.text
    text = credentials.text
    assert "api-secret-must-not-leak" not in text
    assert "OPENEXCHANGERATES_APP_ID" in text
    assert credentials.json()["readiness_claim"] == "configuration_presence_only"

    first = client.get("/providers/evidence", params=params, headers=headers)
    second = client.get("/providers/evidence", params=params, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.content == second.content
    assert "api-secret-must-not-leak" not in first.text
    assert "tenant.evil" not in first.text
    exported = client.get("/providers/evidence/export", params=params, headers=headers)
    assert exported.status_code == 200
    assert exported.headers["X-Evidence-SHA256"] == exported.json()["evidence_sha256"]
    assert exported.headers["Content-Disposition"].endswith(f'provider-governance-{context["org"]}.json"')
