"""Persistent provider governance without broadening executable process trust."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from apps.api.version import API_VERSION
from apps.provider_sdk import PROVIDER_SDK_VERSION, SUPPORTED_CAPABILITIES

from ..audit import get_current_actor
from ..config import ProviderInfo, Settings, settings
from ..limits import MAX_PROVIDER_EVIDENCE_ROWS, MAX_PROVIDER_POLICY_NOTE_LENGTH
from ..models.models import (
    AuditAction,
    AuditLog,
    OrganizationCapabilityDefault,
    OrganizationProviderPolicy,
    TrustedProviderRegistration,
)
from .plugin_loader import (
    ProviderDescriptor,
    ProviderHandle,
    load_provider,
    provider_descriptors,
    refresh_provider_cache,
)

__all__ = [
    "ProviderGovernanceConflictError",
    "ProviderGovernanceError",
    "ProviderGovernanceNotFoundError",
    "ProviderGovernanceService",
    "ProviderGovernanceValidationError",
    "invalidate_governance_cache",
    "reconcile_trusted_catalog",
    "validate_trusted_catalog",
]


class ProviderGovernanceError(ValueError):
    """Base error carrying a stable API-safe domain code."""

    code = "PROVIDER_GOVERNANCE_ERROR"


class ProviderGovernanceNotFoundError(ProviderGovernanceError):
    code = "PROVIDER_GOVERNANCE_NOT_FOUND"


class ProviderGovernanceConflictError(ProviderGovernanceError):
    code = "PROVIDER_GOVERNANCE_CONFLICT"


class ProviderGovernanceValidationError(ProviderGovernanceError):
    code = "PROVIDER_GOVERNANCE_VALIDATION"


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """Bounded deterministic reconciliation evidence."""

    changed: tuple[str, ...]
    unchanged: tuple[str, ...]
    drifted: tuple[str, ...]
    removed: tuple[str, ...]
    conforming: tuple[str, ...]
    incompatible: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "changed": list(self.changed),
            "unchanged": list(self.unchanged),
            "drifted": list(self.drifted),
            "removed": list(self.removed),
            "conforming": list(self.conforming),
            "incompatible": list(self.incompatible),
            "provider_count": len(self.conforming) + len(self.incompatible),
        }


_governance_cache_generation: dict[int, int] = {}


def invalidate_governance_cache(organization_id: int | None = None) -> None:
    """Advance a revision marker only after durable governance commits."""

    key = organization_id or 0
    _governance_cache_generation[key] = _governance_cache_generation.get(key, 0) + 1


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256(payload: object) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _configuration_fingerprint(key: str, info: ProviderInfo) -> str:
    """Hash trusted identity without persisting its importable module path."""

    return _sha256(
        {
            "provider_key": key,
            "trusted_module": info.module,
            "capabilities": sorted(info.capabilities),
        }
    )


def _manifest_fingerprint(descriptor: ProviderDescriptor) -> str | None:
    manifest = descriptor.manifest
    return _sha256(manifest.to_dict()) if manifest is not None else None


def _descriptor_map() -> dict[str, ProviderDescriptor]:
    return {descriptor.metadata.key: descriptor for descriptor in provider_descriptors()}


def _registration_snapshot(row: TrustedProviderRegistration) -> dict[str, object]:
    return {
        "provider_key": row.provider_key,
        "configuration_fingerprint": row.configuration_fingerprint,
        "manifest_fingerprint": row.manifest_fingerprint,
        "capabilities": sorted(row.capabilities),
        "provider_version": row.provider_version,
        "sdk_version": row.sdk_version,
        "api_version": row.api_version,
        "conformance_status": row.conformance_status,
        "compatibility_status": row.compatibility_status,
        "conformance_codes": sorted(row.conformance_codes),
        "lifecycle_status": row.lifecycle_status,
        "revision": row.revision,
    }


def _audit_row(
    *,
    action: AuditAction,
    entity_name: str,
    entity_id: str,
    organization_id: int | None,
    actor_user_id: int | None,
    before: dict[str, object] | None,
    after: dict[str, object] | None,
    event: str,
) -> AuditLog:
    actor = get_current_actor()
    before_map = before or {}
    after_map = after or {}
    diff = {
        key: {"before": before_map.get(key), "after": after_map.get(key)}
        for key in sorted(set(before_map) | set(after_map))
        if before_map.get(key) != after_map.get(key)
    }
    return AuditLog(
        ts=datetime.now(UTC),
        action=action,
        entity_name=entity_name,
        entity_id=entity_id,
        before_state=before,
        after_state=after,
        payload_diff=diff or None,
        request_id=actor.request_id if actor is not None else str(uuid4()),
        actor_user_id=actor_user_id,
        actor_org_id=organization_id,
        actor_label=actor.user_label if actor is not None else None,
        source=actor.source if actor is not None else "operator",
        context={"event": event},
    )


def reconcile_trusted_catalog(
    session: Session,
    *,
    configured_settings: Settings = settings,
    accept_drift: bool = False,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> ReconciliationResult:
    """Reconcile current process trust into safe registration evidence.

    The only import targets inspected by this function originate in the current
    process configuration. Persisted state is never used as an import source.
    """

    descriptors = _descriptor_map()
    existing = {row.provider_key: row for row in session.exec(select(TrustedProviderRegistration))}
    changed: list[str] = []
    unchanged: list[str] = []
    drifted: list[str] = []
    removed: list[str] = []
    conforming: list[str] = []
    incompatible: list[str] = []
    now = clock().astimezone(UTC)

    try:
        for key, info in sorted(configured_settings.allowed_providers.items()):
            descriptor = descriptors[key]
            configuration_fingerprint = _configuration_fingerprint(key, info)
            manifest_fingerprint = _manifest_fingerprint(descriptor)
            passed = descriptor.conformance.passed and descriptor.compatibility.status == "compatible"
            conformance_status = "CONFORMING" if descriptor.conformance.passed else "NONCONFORMING"
            compatibility_status = descriptor.compatibility.status.upper()
            failure_codes = sorted(descriptor.conformance.failure_codes)
            desired_lifecycle = "ACTIVE" if passed else "QUARANTINED"
            (conforming if passed else incompatible).append(key)
            current = existing.get(key)

            if current is None:
                current = TrustedProviderRegistration(
                    provider_key=key,
                    provider_name=descriptor.metadata.name,
                    description=descriptor.metadata.description,
                    configuration_fingerprint=configuration_fingerprint,
                    manifest_fingerprint=manifest_fingerprint,
                    capabilities=sorted(descriptor.metadata.capabilities),
                    provider_version=descriptor.version,
                    sdk_version=(descriptor.manifest.sdk_version if descriptor.manifest is not None else None),
                    api_version=API_VERSION,
                    conformance_status=conformance_status,
                    compatibility_status=compatibility_status,
                    conformance_codes=failure_codes,
                    lifecycle_status=desired_lifecycle,
                    first_seen_at=now,
                    reconciled_at=now,
                )
                session.add(current)
                after = _registration_snapshot(current)
                session.add(
                    _audit_row(
                        action=AuditAction.CREATE,
                        entity_name="TrustedProviderRegistration",
                        entity_id=key,
                        organization_id=None,
                        actor_user_id=None,
                        before=None,
                        after=after,
                        event="provider.catalog.registered",
                    )
                )
                changed.append(key)
                continue

            identity_drift = (
                current.configuration_fingerprint != configuration_fingerprint
                or current.manifest_fingerprint != manifest_fingerprint
                or sorted(current.capabilities) != sorted(descriptor.metadata.capabilities)
            )
            if identity_drift and not accept_drift:
                drifted.append(key)
                if current.lifecycle_status == "QUARANTINED" and current.conformance_status == "DRIFTED":
                    unchanged.append(key)
                    continue
                before = _registration_snapshot(current)
                current.lifecycle_status = "QUARANTINED"
                current.conformance_status = "DRIFTED"
                current.compatibility_status = "INCOMPATIBLE"
                current.conformance_codes = ["registration.identity_drift"]
                current.revision += 1
                current.reconciled_at = now
                session.add(current)
                session.add(
                    _audit_row(
                        action=AuditAction.UPDATE,
                        entity_name="TrustedProviderRegistration",
                        entity_id=key,
                        organization_id=None,
                        actor_user_id=None,
                        before=before,
                        after=_registration_snapshot(current),
                        event="provider.catalog.drift_quarantined",
                    )
                )
                changed.append(key)
                continue

            desired = {
                "provider_name": descriptor.metadata.name,
                "description": descriptor.metadata.description,
                "configuration_fingerprint": configuration_fingerprint,
                "manifest_fingerprint": manifest_fingerprint,
                "capabilities": sorted(descriptor.metadata.capabilities),
                "provider_version": descriptor.version,
                "sdk_version": descriptor.manifest.sdk_version if descriptor.manifest is not None else None,
                "api_version": API_VERSION,
                "conformance_status": conformance_status,
                "compatibility_status": compatibility_status,
                "conformance_codes": failure_codes,
                "lifecycle_status": desired_lifecycle,
            }
            if all(getattr(current, field) == value for field, value in desired.items()):
                unchanged.append(key)
                continue
            before = _registration_snapshot(current)
            for field, value in desired.items():
                setattr(current, field, value)
            current.revision += 1
            current.reconciled_at = now
            session.add(current)
            session.add(
                _audit_row(
                    action=AuditAction.UPDATE,
                    entity_name="TrustedProviderRegistration",
                    entity_id=key,
                    organization_id=None,
                    actor_user_id=None,
                    before=before,
                    after=_registration_snapshot(current),
                    event="provider.catalog.reconciled",
                )
            )
            changed.append(key)

        trusted_keys = set(configured_settings.allowed_providers)
        for key, current in sorted(existing.items()):
            if key in trusted_keys:
                continue
            removed.append(key)
            if current.lifecycle_status == "REMOVED":
                unchanged.append(key)
                continue
            before = _registration_snapshot(current)
            current.lifecycle_status = "REMOVED"
            current.conformance_status = "UNAVAILABLE"
            current.compatibility_status = "INCOMPATIBLE"
            current.conformance_codes = ["registration.not_process_trusted"]
            current.revision += 1
            current.reconciled_at = now
            session.add(current)
            session.add(
                _audit_row(
                    action=AuditAction.UPDATE,
                    entity_name="TrustedProviderRegistration",
                    entity_id=key,
                    organization_id=None,
                    actor_user_id=None,
                    before=before,
                    after=_registration_snapshot(current),
                    event="provider.catalog.removed_from_process_trust",
                )
            )
            changed.append(key)

        session.commit()
    except Exception:
        session.rollback()
        raise

    refresh_provider_cache()
    invalidate_governance_cache()
    return ReconciliationResult(
        changed=tuple(sorted(set(changed))),
        unchanged=tuple(sorted(set(unchanged))),
        drifted=tuple(sorted(set(drifted))),
        removed=tuple(sorted(set(removed))),
        conforming=tuple(sorted(set(conforming))),
        incompatible=tuple(sorted(set(incompatible))),
    )


def validate_trusted_catalog(
    session: Session,
    *,
    configured_settings: Settings = settings,
) -> dict[str, object]:
    """Compare persisted evidence with current trust without mutating state."""

    descriptors = _descriptor_map()
    registrations = {row.provider_key: row for row in session.exec(select(TrustedProviderRegistration))}
    reports: list[dict[str, object]] = []
    for key, info in sorted(configured_settings.allowed_providers.items()):
        descriptor = descriptors[key]
        registration = registrations.get(key)
        codes: list[str] = []
        if registration is None:
            codes.append("registration.missing")
        else:
            if registration.configuration_fingerprint != _configuration_fingerprint(key, info):
                codes.append("registration.configuration_drift")
            if registration.manifest_fingerprint != _manifest_fingerprint(descriptor):
                codes.append("registration.manifest_drift")
            if registration.lifecycle_status != "ACTIVE":
                codes.append("registration.not_active")
        codes.extend(descriptor.conformance.failure_codes)
        if descriptor.compatibility.status != "compatible":
            codes.append("registration.incompatible")
        reports.append({"provider_key": key, "valid": not codes, "codes": sorted(set(codes))})

    for key in sorted(set(registrations) - set(configured_settings.allowed_providers)):
        reports.append(
            {
                "provider_key": key,
                "valid": False,
                "codes": ["registration.not_process_trusted"],
            }
        )
    return {"valid": all(bool(item["valid"]) for item in reports), "reports": reports}


class ProviderGovernanceService:
    """Authoritative tenant provider catalog, policy, and resolution boundary."""

    def __init__(
        self,
        session: Session,
        organization_id: int,
        actor_user_id: int,
        *,
        configured_settings: Settings = settings,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self.s = session
        self.organization_id = organization_id
        self.actor_user_id = actor_user_id
        self.settings = configured_settings
        self.environ = environ if environ is not None else os.environ

    @staticmethod
    def _normalise_note(note: str | None) -> str | None:
        if note is None:
            return None
        normalized = note.strip()
        if not normalized:
            return None
        if len(normalized) > MAX_PROVIDER_POLICY_NOTE_LENGTH:
            raise ProviderGovernanceValidationError(
                f"Policy note must not exceed {MAX_PROVIDER_POLICY_NOTE_LENGTH} characters"
            )
        return normalized

    @staticmethod
    def _row_capabilities(row: Mapping[str, object]) -> tuple[str, ...]:
        value = row.get("capabilities")
        if not isinstance(value, (list, tuple)):
            return ()
        return tuple(str(item) for item in value)

    def _registrations(self) -> dict[str, TrustedProviderRegistration]:
        return {row.provider_key: row for row in self.s.exec(select(TrustedProviderRegistration))}

    def _policies(self) -> dict[str, OrganizationProviderPolicy]:
        statement = select(OrganizationProviderPolicy).where(
            OrganizationProviderPolicy.organization_id == self.organization_id
        )
        return {row.provider_key: row for row in self.s.exec(statement)}

    def _defaults(self) -> dict[str, OrganizationCapabilityDefault]:
        statement = select(OrganizationCapabilityDefault).where(
            OrganizationCapabilityDefault.organization_id == self.organization_id
        )
        return {row.capability: row for row in self.s.exec(statement)}

    def _descriptor_state(
        self,
        descriptor: ProviderDescriptor,
        registration: TrustedProviderRegistration | None,
        policy: OrganizationProviderPolicy | None,
    ) -> tuple[bool, list[str]]:
        key = descriptor.metadata.key
        info = self.settings.allowed_providers.get(key)
        reasons: list[str] = []
        if info is None:
            reasons.append("not_process_trusted")
        if registration is None:
            reasons.append("not_reconciled")
        elif info is not None:
            if registration.configuration_fingerprint != _configuration_fingerprint(key, info):
                reasons.append("configuration_drift")
            if registration.manifest_fingerprint != _manifest_fingerprint(descriptor):
                reasons.append("manifest_drift")
            if registration.lifecycle_status != "ACTIVE":
                reasons.append(registration.lifecycle_status.lower())
        if not descriptor.conformance.passed:
            reasons.append("nonconforming")
        if descriptor.compatibility.status != "compatible":
            reasons.append("incompatible")
        if policy is not None and not policy.enabled:
            reasons.append("disabled")
        return not reasons, sorted(set(reasons))

    def catalog(self) -> list[dict[str, object]]:
        descriptors = _descriptor_map()
        registrations = self._registrations()
        policies = self._policies()
        defaults = self._defaults()
        rows: list[dict[str, object]] = []
        effective_by_key: dict[str, bool] = {}

        for key, descriptor in sorted(descriptors.items()):
            registration = registrations.get(key)
            policy = policies.get(key)
            effective, reasons = self._descriptor_state(descriptor, registration, policy)
            effective_by_key[key] = effective
            manifest = descriptor.manifest
            credentials = [
                {"name": name, "present": bool((self.environ.get(name) or "").strip())}
                for name in (manifest.credential_env if manifest is not None else ())
            ]
            rows.append(
                {
                    "provider_key": key,
                    "name": descriptor.metadata.name,
                    "description": descriptor.metadata.description,
                    "capabilities": list(descriptor.metadata.capabilities),
                    "process_trusted": True,
                    "source": "operator_process_allowlist",
                    "configuration_fingerprint": (
                        registration.configuration_fingerprint if registration is not None else None
                    ),
                    "manifest_fingerprint": registration.manifest_fingerprint if registration is not None else None,
                    "provider_version": descriptor.version,
                    "sdk_version": manifest.sdk_version if manifest is not None else PROVIDER_SDK_VERSION,
                    "api_version": API_VERSION,
                    "conforming": descriptor.conformance.passed,
                    "conformance_codes": list(descriptor.conformance.failure_codes),
                    "compatibility": descriptor.compatibility.to_dict(),
                    "lifecycle_status": registration.lifecycle_status if registration is not None else "UNRECONCILED",
                    "registration_revision": registration.revision if registration is not None else None,
                    "enabled": policy.enabled if policy is not None else True,
                    "policy_explicit": policy is not None,
                    "policy_note": policy.note if policy is not None else None,
                    "policy_revision": policy.revision if policy is not None else 0,
                    "policy_audit_reference": policy.audit_reference if policy is not None else None,
                    "credential_requirements": credentials,
                    "credential_ready": all(bool(item["present"]) for item in credentials),
                    "credential_readiness_claim": "configuration_presence_only",
                    "effective": effective,
                    "blocked_reasons": reasons,
                    "default_capabilities": [],
                    "next_action": self._next_action(reasons),
                    "technical": {
                        "checks": [check.to_dict() for check in descriptor.conformance.checks],
                    },
                }
            )

        valid_defaults: dict[str, str] = {}
        for capability, default in sorted(defaults.items()):
            selected_descriptor = descriptors.get(default.provider_key)
            if (
                selected_descriptor is not None
                and capability in selected_descriptor.metadata.capabilities
                and effective_by_key.get(default.provider_key, False)
            ):
                valid_defaults[capability] = default.provider_key
        for row in rows:
            key = str(row["provider_key"])
            row["default_capabilities"] = [
                capability for capability, provider_key in valid_defaults.items() if provider_key == key
            ]

        for key, registration in sorted(registrations.items()):
            if key in descriptors:
                continue
            policy = policies.get(key)
            rows.append(
                {
                    "provider_key": key,
                    "name": registration.provider_name,
                    "description": registration.description,
                    "capabilities": sorted(registration.capabilities),
                    "process_trusted": False,
                    "source": "historical_registration_evidence",
                    "configuration_fingerprint": registration.configuration_fingerprint,
                    "manifest_fingerprint": registration.manifest_fingerprint,
                    "provider_version": registration.provider_version,
                    "sdk_version": registration.sdk_version,
                    "api_version": registration.api_version,
                    "conforming": False,
                    "conformance_codes": ["registration.not_process_trusted"],
                    "compatibility": {"status": "incompatible", "reason": "not process trusted"},
                    "lifecycle_status": registration.lifecycle_status,
                    "registration_revision": registration.revision,
                    "enabled": policy.enabled if policy is not None else True,
                    "policy_explicit": policy is not None,
                    "policy_note": policy.note if policy is not None else None,
                    "policy_revision": policy.revision if policy is not None else 0,
                    "policy_audit_reference": policy.audit_reference if policy is not None else None,
                    "credential_requirements": [],
                    "credential_ready": False,
                    "credential_readiness_claim": "configuration_presence_only",
                    "effective": False,
                    "blocked_reasons": ["not_process_trusted"],
                    "default_capabilities": [],
                    "next_action": "Operator must restore explicit process trust and reconcile.",
                    "technical": {"checks": []},
                }
            )
        return rows[:MAX_PROVIDER_EVIDENCE_ROWS]

    @staticmethod
    def _next_action(reasons: list[str]) -> str:
        if not reasons:
            return "Provider is available for governed use."
        if "disabled" in reasons:
            return "An organization administrator may enable this trusted provider."
        if "not_reconciled" in reasons:
            return "An operator must reconcile the process-trusted catalog."
        if "configuration_drift" in reasons or "manifest_drift" in reasons or "quarantined" in reasons:
            return "An operator must review drift and explicitly accept a trusted reconciliation."
        return "An operator must correct provider trust or conformance before use."

    def detail(self, provider_key: str) -> dict[str, object]:
        for row in self.catalog():
            if row["provider_key"] == provider_key:
                return row
        raise ProviderGovernanceNotFoundError("Provider not found")

    def policy_snapshot(self) -> dict[str, object]:
        policies = self._policies()
        defaults = self._defaults()
        catalog = self.catalog()
        effective = {str(row["provider_key"]): bool(row["effective"]) for row in catalog}
        capabilities = {str(row["provider_key"]): set(self._row_capabilities(row)) for row in catalog}
        default_rows = []
        for capability, default in sorted(defaults.items()):
            is_effective = effective.get(default.provider_key, False) and capability in capabilities.get(
                default.provider_key, set()
            )
            default_rows.append(
                {
                    "capability": capability,
                    "provider_key": default.provider_key,
                    "revision": default.revision,
                    "audit_reference": default.audit_reference,
                    "effective": is_effective,
                }
            )
        return {
            "organization_id": self.organization_id,
            "policies": [
                {
                    "provider_key": key,
                    "enabled": policy.enabled,
                    "note": policy.note,
                    "revision": policy.revision,
                    "audit_reference": policy.audit_reference,
                    "created_at": policy.created_at.isoformat(),
                    "updated_at": policy.updated_at.isoformat(),
                }
                for key, policy in sorted(policies.items())
            ],
            "defaults": default_rows,
        }

    def _require_process_trusted(self, provider_key: str) -> None:
        if provider_key not in self.settings.allowed_providers:
            raise ProviderGovernanceNotFoundError("Provider not found")

    def update_policy(
        self,
        provider_key: str,
        *,
        enabled: bool,
        note: str | None,
        expected_revision: int | None,
    ) -> dict[str, object]:
        self._require_process_trusted(provider_key)
        normalized_note = self._normalise_note(note)
        current = self._policies().get(provider_key)
        now = datetime.now(UTC)
        try:
            if current is None:
                if expected_revision not in (None, 0):
                    raise ProviderGovernanceConflictError("Provider policy revision is stale")
                current = OrganizationProviderPolicy(
                    organization_id=self.organization_id,
                    provider_key=provider_key,
                    enabled=enabled,
                    note=normalized_note,
                    created_at=now,
                    updated_at=now,
                    created_by_id=self.actor_user_id,
                    updated_by_id=self.actor_user_id,
                )
                self.s.add(current)
                self.s.flush()
                before = None
                action = AuditAction.CREATE
            else:
                if expected_revision is None or expected_revision != current.revision:
                    raise ProviderGovernanceConflictError("Provider policy revision is stale")
                before = self._policy_dict(current)
                result = self.s.exec(
                    update(OrganizationProviderPolicy)
                    .where(
                        cast(Any, OrganizationProviderPolicy.organization_id) == self.organization_id,
                        cast(Any, OrganizationProviderPolicy.provider_key) == provider_key,
                        cast(Any, OrganizationProviderPolicy.revision) == expected_revision,
                    )
                    .values(
                        enabled=enabled,
                        note=normalized_note,
                        revision=expected_revision + 1,
                        updated_at=now,
                        updated_by_id=self.actor_user_id,
                    )
                    .execution_options(synchronize_session=False)
                )
                if getattr(result, "rowcount", 0) != 1:
                    raise ProviderGovernanceConflictError("Provider policy revision is stale")
                self.s.expire_all()
                current = self._policies()[provider_key]
                action = AuditAction.UPDATE
            after = self._policy_dict(current)
            audit = _audit_row(
                action=action,
                entity_name="OrganizationProviderPolicy",
                entity_id=provider_key,
                organization_id=self.organization_id,
                actor_user_id=self.actor_user_id,
                before=before,
                after=after,
                event="provider.policy.updated",
            )
            self.s.add(audit)
            self.s.flush()
            current.audit_reference = str(audit.id)
            self.s.add(current)
            self.s.commit()
            self.s.refresh(current)
        except ProviderGovernanceError:
            self.s.rollback()
            raise
        except IntegrityError as exc:
            self.s.rollback()
            raise ProviderGovernanceConflictError("Provider policy revision is stale") from exc
        except Exception:
            self.s.rollback()
            raise
        invalidate_governance_cache(self.organization_id)
        return self._policy_dict(current)

    @staticmethod
    def _policy_dict(policy: OrganizationProviderPolicy) -> dict[str, object]:
        return {
            "provider_key": policy.provider_key,
            "enabled": policy.enabled,
            "note": policy.note,
            "revision": policy.revision,
            "audit_reference": policy.audit_reference,
        }

    def set_default(
        self,
        capability: str,
        provider_key: str,
        *,
        expected_revision: int | None,
    ) -> dict[str, object]:
        if capability not in SUPPORTED_CAPABILITIES:
            raise ProviderGovernanceValidationError("Unsupported provider capability")
        self._require_process_trusted(provider_key)
        detail = self.detail(provider_key)
        if capability not in self._row_capabilities(detail):
            raise ProviderGovernanceValidationError("Provider does not support the requested capability")
        if not detail["effective"]:
            raise ProviderGovernanceConflictError("Provider is not effective for this organization")
        current = self._defaults().get(capability)
        now = datetime.now(UTC)
        try:
            if current is None:
                if expected_revision not in (None, 0):
                    raise ProviderGovernanceConflictError("Provider default revision is stale")
                current = OrganizationCapabilityDefault(
                    organization_id=self.organization_id,
                    capability=capability,
                    provider_key=provider_key,
                    created_at=now,
                    updated_at=now,
                    created_by_id=self.actor_user_id,
                    updated_by_id=self.actor_user_id,
                )
                self.s.add(current)
                self.s.flush()
                before = None
                action = AuditAction.CREATE
            else:
                if expected_revision is None or expected_revision != current.revision:
                    raise ProviderGovernanceConflictError("Provider default revision is stale")
                before = self._default_dict(current, effective=True)
                result = self.s.exec(
                    update(OrganizationCapabilityDefault)
                    .where(
                        cast(Any, OrganizationCapabilityDefault.organization_id) == self.organization_id,
                        cast(Any, OrganizationCapabilityDefault.capability) == capability,
                        cast(Any, OrganizationCapabilityDefault.revision) == expected_revision,
                    )
                    .values(
                        provider_key=provider_key,
                        revision=expected_revision + 1,
                        updated_at=now,
                        updated_by_id=self.actor_user_id,
                    )
                    .execution_options(synchronize_session=False)
                )
                if getattr(result, "rowcount", 0) != 1:
                    raise ProviderGovernanceConflictError("Provider default revision is stale")
                self.s.expire_all()
                current = self._defaults()[capability]
                action = AuditAction.UPDATE
            after = self._default_dict(current, effective=True)
            audit = _audit_row(
                action=action,
                entity_name="OrganizationCapabilityDefault",
                entity_id=capability,
                organization_id=self.organization_id,
                actor_user_id=self.actor_user_id,
                before=before,
                after=after,
                event="provider.default.updated",
            )
            self.s.add(audit)
            self.s.flush()
            current.audit_reference = str(audit.id)
            self.s.add(current)
            self.s.commit()
            self.s.refresh(current)
        except ProviderGovernanceError:
            self.s.rollback()
            raise
        except IntegrityError as exc:
            self.s.rollback()
            raise ProviderGovernanceConflictError("Provider default revision is stale") from exc
        except Exception:
            self.s.rollback()
            raise
        invalidate_governance_cache(self.organization_id)
        return self._default_dict(current, effective=True)

    def clear_default(self, capability: str, *, expected_revision: int) -> dict[str, object]:
        current = self._defaults().get(capability)
        if current is None:
            raise ProviderGovernanceNotFoundError("Provider default not found")
        if current.revision != expected_revision:
            raise ProviderGovernanceConflictError("Provider default revision is stale")
        before = self._default_dict(current, effective=True)
        try:
            result = self.s.exec(
                delete(OrganizationCapabilityDefault).where(
                    cast(Any, OrganizationCapabilityDefault.organization_id) == self.organization_id,
                    cast(Any, OrganizationCapabilityDefault.capability) == capability,
                    cast(Any, OrganizationCapabilityDefault.revision) == expected_revision,
                )
            )
            if getattr(result, "rowcount", 0) != 1:
                raise ProviderGovernanceConflictError("Provider default revision is stale")
            self.s.add(
                _audit_row(
                    action=AuditAction.DELETE,
                    entity_name="OrganizationCapabilityDefault",
                    entity_id=capability,
                    organization_id=self.organization_id,
                    actor_user_id=self.actor_user_id,
                    before=before,
                    after=None,
                    event="provider.default.cleared",
                )
            )
            self.s.commit()
        except ProviderGovernanceError:
            self.s.rollback()
            raise
        except Exception:
            self.s.rollback()
            raise
        invalidate_governance_cache(self.organization_id)
        return {"capability": capability, "cleared": True, "revision": expected_revision}

    @staticmethod
    def _default_dict(default: OrganizationCapabilityDefault, *, effective: bool) -> dict[str, object]:
        return {
            "capability": default.capability,
            "provider_key": default.provider_key,
            "revision": default.revision,
            "audit_reference": default.audit_reference,
            "effective": effective,
        }

    def resolve_provider(self, capability: str, explicit_key: str | None = None) -> ProviderHandle:
        if capability not in SUPPORTED_CAPABILITIES:
            raise ProviderGovernanceValidationError("Unsupported provider capability")
        catalog = self.catalog()
        by_key = {str(row["provider_key"]): row for row in catalog}
        if explicit_key is not None:
            selected_key = explicit_key
            row = by_key.get(selected_key)
            if row is None:
                raise ProviderGovernanceNotFoundError("Provider not found")
            if not row["process_trusted"]:
                raise ProviderGovernanceNotFoundError("Provider not found")
            if capability not in self._row_capabilities(row):
                raise ProviderGovernanceValidationError("Provider does not support the requested capability")
            if not row["effective"]:
                raise ProviderGovernanceConflictError("Provider is not effective for this organization")
            selection_source = "explicit"
        else:
            selected_key = ""
            selection_source = "deterministic_fallback"
            default = self._defaults().get(capability)
            if default is not None:
                row = by_key.get(default.provider_key)
                if row is not None and capability in self._row_capabilities(row) and row["effective"]:
                    selected_key = default.provider_key
                    selection_source = "organization_default"
            if not selected_key:
                candidates = sorted(
                    key
                    for key, row in by_key.items()
                    if capability in self._row_capabilities(row) and bool(row["effective"])
                )
                if not candidates:
                    raise ProviderGovernanceConflictError(
                        "No effective provider is available for the requested capability"
                    )
                selected_key = candidates[0]

        # This is the only construction step. load_provider resolves its import
        # target again from current settings.allowed_providers, never persistence.
        try:
            handle = load_provider(selected_key)
        except ValueError as exc:
            raise ProviderGovernanceConflictError("Provider construction failed") from exc
        selected = by_key[selected_key]
        governance = {
            "organization_id": self.organization_id,
            "provider_key": selected_key,
            "capability": capability,
            "selection_source": selection_source,
            "registration_revision": selected["registration_revision"],
            "policy_revision": selected["policy_revision"],
            "source": "operator_process_allowlist_intersected_with_organization_policy",
        }
        return replace(handle, governance=governance)

    def evidence(self) -> dict[str, object]:
        catalog = self.catalog()
        policy = self.policy_snapshot()
        payload: dict[str, object] = {
            "schema_version": "provider-governance-evidence-v1",
            "organization_id": self.organization_id,
            "application_api_version": API_VERSION,
            "provider_sdk_version": PROVIDER_SDK_VERSION,
            "providers": catalog,
            "policies": policy["policies"],
            "defaults": policy["defaults"],
        }
        payload["evidence_sha256"] = _sha256(payload)
        return payload

    def evidence_json(self) -> str:
        return json.dumps(self.evidence(), indent=2, sort_keys=True, ensure_ascii=True) + "\n"
