"""Deterministic persistence and trust-boundary coverage for provider governance."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from apps.api.config import settings
from apps.api.models.models import (
    AuditLog,
    Membership,
    Organization,
    OrganizationProviderPolicy,
    TrustedProviderRegistration,
    User,
)
from apps.api.services import provider_governance_service as governance_module
from apps.api.services.plugin_loader import ProviderHandle, ProviderMetadata, refresh_provider_cache
from apps.api.services.provider_governance_service import (
    ProviderGovernanceConflictError,
    ProviderGovernanceNotFoundError,
    ProviderGovernanceService,
    reconcile_trusted_catalog,
    validate_trusted_catalog,
)
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select


@contextmanager
def governance_session() -> Iterator[tuple[Session, int, int]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        organization = Organization(name="Provider Governance Org")
        administrator = User(email="provider-admin@example.test", password_hash="stub")
        session.add_all([organization, administrator])
        session.commit()
        session.refresh(organization)
        session.refresh(administrator)
        assert organization.id is not None
        assert administrator.id is not None
        session.add(
            Membership(
                organization_id=organization.id,
                user_id=administrator.id,
                is_admin=True,
            )
        )
        session.commit()
        yield session, organization.id, administrator.id
    engine.dispose()


def test_catalog_bootstrap_is_idempotent_and_persists_across_fresh_sessions() -> None:
    with governance_session() as (session, organization_id, actor_id):
        first = reconcile_trusted_catalog(session)
        second = reconcile_trusted_catalog(session)

        assert first.changed == tuple(sorted(settings.allowed_providers))
        assert second.changed == ()
        assert set(second.unchanged) == set(settings.allowed_providers)
        registrations = list(session.exec(select(TrustedProviderRegistration)))
        assert len(registrations) == len(settings.allowed_providers)
        assert all(row.lifecycle_status == "ACTIVE" for row in registrations)
        assert all(len(row.configuration_fingerprint) == 64 for row in registrations)
        assert "module" not in TrustedProviderRegistration.model_fields

        bind = session.get_bind()
        assert bind is not None
        with Session(bind, expire_on_commit=False) as fresh:
            catalog = ProviderGovernanceService(fresh, organization_id, actor_id).catalog()
        assert len(catalog) == len(settings.allowed_providers)
        assert all(row["process_trusted"] for row in catalog)


def test_process_allowlist_removal_overrides_historical_persistence(monkeypatch: pytest.MonkeyPatch) -> None:
    with governance_session() as (session, organization_id, actor_id):
        reconcile_trusted_catalog(session)
        reduced = dict(settings.allowed_providers)
        reduced.pop("fx:ecb")
        monkeypatch.setattr(settings, "allowed_providers", reduced)
        refresh_provider_cache()

        result = reconcile_trusted_catalog(session)
        registration = session.get(TrustedProviderRegistration, "fx:ecb")
        assert registration is not None
        assert registration.lifecycle_status == "REMOVED"
        assert "fx:ecb" in result.removed
        service = ProviderGovernanceService(session, organization_id, actor_id)
        with pytest.raises(ProviderGovernanceNotFoundError, match="not found"):
            service.resolve_provider("fx", "fx:ecb")
        historical = service.detail("fx:ecb")
        assert historical["process_trusted"] is False
        assert historical["effective"] is False


def test_persisted_arbitrary_identity_never_becomes_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    with governance_session() as (session, organization_id, actor_id):
        session.add(
            TrustedProviderRegistration(
                provider_key="market:tenant_evil",
                provider_name="Tenant supplied",
                configuration_fingerprint="a" * 64,
                manifest_fingerprint="b" * 64,
                capabilities=["market"],
                api_version="0.0.0",
                conformance_status="CONFORMING",
                compatibility_status="COMPATIBLE",
                lifecycle_status="ACTIVE",
            )
        )
        session.commit()
        calls: list[str] = []

        def forbidden_load(key: str):
            calls.append(key)
            raise AssertionError("persisted identity must not reach the loader")

        monkeypatch.setattr(governance_module, "load_provider", forbidden_load)
        service = ProviderGovernanceService(session, organization_id, actor_id)
        with pytest.raises(ProviderGovernanceNotFoundError):
            service.resolve_provider("market", "market:tenant_evil")
        assert calls == []


def test_manifest_drift_quarantines_and_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    with governance_session() as (session, organization_id, actor_id):
        reconcile_trusted_catalog(session)
        registration = session.get(TrustedProviderRegistration, "market:commodities_demo")
        assert registration is not None
        registration.manifest_fingerprint = "0" * 64
        session.add(registration)
        session.commit()

        calls: list[str] = []
        monkeypatch.setattr(governance_module, "load_provider", lambda key: calls.append(key))
        service = ProviderGovernanceService(session, organization_id, actor_id)
        with pytest.raises(ProviderGovernanceConflictError, match="not effective"):
            service.resolve_provider("market", "market:commodities_demo")
        assert calls == []

        result = reconcile_trusted_catalog(session)
        session.refresh(registration)
        assert "market:commodities_demo" in result.drifted
        assert registration.lifecycle_status == "QUARANTINED"
        assert registration.conformance_status == "DRIFTED"
        accepted = reconcile_trusted_catalog(session, accept_drift=True)
        session.refresh(registration)
        assert "market:commodities_demo" in accepted.changed
        assert registration.lifecycle_status == "ACTIVE"


def test_policy_defaults_cas_audit_and_invalidated_default_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    with governance_session() as (session, organization_id, actor_id):
        reconcile_trusted_catalog(session)
        service = ProviderGovernanceService(session, organization_id, actor_id)

        policy = service.update_policy("fx:ecb", enabled=True, note="Primary reference", expected_revision=0)
        assert policy["revision"] == 1
        default = service.set_default("fx", "fx:ecb", expected_revision=0)
        assert default["revision"] == 1
        handle = service.resolve_provider("fx")
        assert handle.metadata.key == "fx:ecb"
        assert handle.governance is not None
        assert handle.governance["selection_source"] == "organization_default"

        with pytest.raises(ProviderGovernanceConflictError, match="stale"):
            service.update_policy("fx:ecb", enabled=False, note=None, expected_revision=0)
        disabled = service.update_policy("fx:ecb", enabled=False, note="Disabled for review", expected_revision=1)
        assert disabled["revision"] == 2
        with pytest.raises(ProviderGovernanceConflictError, match="not effective"):
            service.resolve_provider("fx", "fx:ecb")

        monkeypatch.setattr(
            governance_module,
            "load_provider",
            lambda key: ProviderHandle(
                instance=object(),
                metadata=ProviderMetadata(key=key, name=key, description=None, capabilities=("fx",)),
            ),
        )
        fallback = service.resolve_provider("fx")
        assert fallback.metadata.key == "fx:openexchangerates"
        snapshot = service.policy_snapshot()
        assert snapshot["defaults"][0]["effective"] is False
        audits = list(
            session.exec(
                select(AuditLog).where(
                    AuditLog.actor_org_id == organization_id,
                    AuditLog.entity_name.in_(["OrganizationProviderPolicy", "OrganizationCapabilityDefault"]),
                )
            )
        )
        assert len(audits) == 3
        assert all(row.actor_user_id == actor_id for row in audits)


def test_failed_commit_rolls_back_and_does_not_invalidate_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    with governance_session() as (session, organization_id, actor_id):
        reconcile_trusted_catalog(session)
        invalidations: list[int | None] = []
        monkeypatch.setattr(governance_module, "invalidate_governance_cache", invalidations.append)
        original_commit = session.commit

        def fail_commit() -> None:
            raise RuntimeError("database write failed")

        monkeypatch.setattr(session, "commit", fail_commit)
        service = ProviderGovernanceService(session, organization_id, actor_id)
        with pytest.raises(RuntimeError, match="database write failed"):
            service.update_policy("tax:oecd_demo", enabled=False, note=None, expected_revision=0)
        monkeypatch.setattr(session, "commit", original_commit)
        assert invalidations == []
        assert (
            session.exec(
                select(OrganizationProviderPolicy).where(
                    OrganizationProviderPolicy.organization_id == organization_id,
                    OrganizationProviderPolicy.provider_key == "tax:oecd_demo",
                )
            ).first()
            is None
        )
        assert (
            session.exec(
                select(AuditLog).where(
                    AuditLog.actor_org_id == organization_id,
                    AuditLog.entity_name == "OrganizationProviderPolicy",
                )
            ).first()
            is None
        )


def test_credential_readiness_and_evidence_never_include_values(monkeypatch: pytest.MonkeyPatch) -> None:
    secret_value = "credential-value-must-never-leak"
    monkeypatch.setenv("OPENEXCHANGERATES_APP_ID", secret_value)
    with governance_session() as (session, organization_id, actor_id):
        reconcile_trusted_catalog(session)
        service = ProviderGovernanceService(session, organization_id, actor_id)
        detail = service.detail("fx:openexchangerates")
        assert detail["credential_requirements"] == [{"name": "OPENEXCHANGERATES_APP_ID", "present": True}]
        first = service.evidence_json()
        second = service.evidence_json()
        assert first == second
        assert secret_value not in first
        assert "OPENEXCHANGERATES_APP_ID" in first
        assert "plugins.fx_openexchangerates.provider" not in first
        assert "Authorization" not in first


def test_validation_reports_registration_drift_without_mutation() -> None:
    with governance_session() as (session, _organization_id, _actor_id):
        reconcile_trusted_catalog(session)
        registration = session.get(TrustedProviderRegistration, "tax:oecd_demo")
        assert registration is not None
        original_revision = registration.revision
        registration.configuration_fingerprint = "f" * 64
        session.add(registration)
        session.commit()
        evidence = validate_trusted_catalog(session)
        report = next(item for item in evidence["reports"] if item["provider_key"] == "tax:oecd_demo")
        assert report["valid"] is False
        assert "registration.configuration_drift" in report["codes"]
        session.refresh(registration)
        assert registration.revision == original_revision
