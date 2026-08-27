"""Authenticated organization provider-governance API."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select

from ..dependencies import session_with_audit_context
from ..limits import MAX_PROVIDER_KEY_LENGTH, MAX_PROVIDER_POLICY_NOTE_LENGTH
from ..models.models import Membership, User
from ..security import OrganizationContext, get_current_organization, get_current_user
from ..services.provider_governance_service import (
    ProviderGovernanceConflictError,
    ProviderGovernanceError,
    ProviderGovernanceNotFoundError,
    ProviderGovernanceService,
    ProviderGovernanceValidationError,
)

router = APIRouter(prefix="/providers", tags=["providers"])


class PolicyMutation(BaseModel):
    """Bounded tenant policy mutation; executable module identity is not accepted."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    note: str | None = Field(default=None, max_length=MAX_PROVIDER_POLICY_NOTE_LENGTH)
    revision: int | None = Field(default=None, ge=0, le=2_147_483_647)


class DefaultMutation(BaseModel):
    """Bounded capability-default mutation."""

    model_config = ConfigDict(extra="forbid")

    provider_key: str = Field(min_length=1, max_length=MAX_PROVIDER_KEY_LENGTH)
    revision: int | None = Field(default=None, ge=0, le=2_147_483_647)


def _domain_error(exc: ProviderGovernanceError) -> HTTPException:
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    if isinstance(exc, ProviderGovernanceNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, ProviderGovernanceConflictError):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(exc, ProviderGovernanceValidationError):
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    return HTTPException(status_code=status_code, detail={"code": exc.code, "message": str(exc)})


def _organization_context(
    organization_id: int,
    session: Session,
    current_user: User,
) -> OrganizationContext:
    """Authorize membership nondisclosingly before any provider inspection."""

    if current_user.id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
    membership = session.exec(
        select(Membership).where(
            Membership.organization_id == organization_id,
            Membership.user_id == current_user.id,
        )
    ).first()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return get_current_organization(
        organization_id=organization_id,
        session=session,
        current_user=current_user,
    )


def _service(
    organization_id: int,
    session: Session,
    current_user: User,
) -> tuple[ProviderGovernanceService, OrganizationContext]:
    context = _organization_context(organization_id, session, current_user)
    if current_user.id is None or context.organization.id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Organization context unavailable"
        )
    return ProviderGovernanceService(session, context.organization.id, current_user.id), context


def _require_admin(context: OrganizationContext) -> None:
    if not context.membership.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization administrator access is required",
        )


@router.get("")
def list_catalog(
    organization_id: Annotated[int, Query(ge=1)],
    session: Session = Depends(session_with_audit_context),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    """List current and historical safe provider governance state."""

    service, context = _service(organization_id, session, current_user)
    return {
        "organization_id": organization_id,
        "can_manage": context.membership.is_admin,
        "providers": service.catalog(),
    }


@router.get("/policies")
def list_policies(
    organization_id: Annotated[int, Query(ge=1)],
    session: Session = Depends(session_with_audit_context),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    service, _ = _service(organization_id, session, current_user)
    return service.policy_snapshot()


@router.get("/credentials")
def credential_readiness(
    organization_id: Annotated[int, Query(ge=1)],
    session: Session = Depends(session_with_audit_context),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    service, _ = _service(organization_id, session, current_user)
    return {
        "organization_id": organization_id,
        "readiness_claim": "configuration_presence_only",
        "providers": [
            {
                "provider_key": row["provider_key"],
                "credential_requirements": row["credential_requirements"],
                "credential_ready": row["credential_ready"],
            }
            for row in service.catalog()
        ],
    }


@router.get("/evidence")
def evidence_preview(
    organization_id: Annotated[int, Query(ge=1)],
    session: Session = Depends(session_with_audit_context),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    service, _ = _service(organization_id, session, current_user)
    return service.evidence()


@router.get("/evidence/export")
def evidence_export(
    organization_id: Annotated[int, Query(ge=1)],
    session: Session = Depends(session_with_audit_context),
    current_user: User = Depends(get_current_user),
) -> Response:
    service, _ = _service(organization_id, session, current_user)
    return Response(
        content=service.evidence_json(),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="provider-governance-{organization_id}.json"',
            "X-Evidence-SHA256": str(service.evidence()["evidence_sha256"]),
        },
    )


@router.put("/defaults/{capability}")
def set_capability_default(
    capability: str,
    payload: DefaultMutation,
    organization_id: Annotated[int, Query(ge=1)],
    session: Session = Depends(session_with_audit_context),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    service, context = _service(organization_id, session, current_user)
    _require_admin(context)
    try:
        return service.set_default(
            capability,
            payload.provider_key,
            expected_revision=payload.revision,
        )
    except ProviderGovernanceError as exc:
        raise _domain_error(exc) from exc


@router.delete("/defaults/{capability}")
def clear_capability_default(
    capability: str,
    organization_id: Annotated[int, Query(ge=1)],
    revision: Annotated[int, Query(ge=1, le=2_147_483_647)],
    session: Session = Depends(session_with_audit_context),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    service, context = _service(organization_id, session, current_user)
    _require_admin(context)
    try:
        return service.clear_default(capability, expected_revision=revision)
    except ProviderGovernanceError as exc:
        raise _domain_error(exc) from exc


@router.put("/{provider_key}/policy")
def update_provider_policy(
    provider_key: str,
    payload: PolicyMutation,
    organization_id: Annotated[int, Query(ge=1)],
    session: Session = Depends(session_with_audit_context),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    service, context = _service(organization_id, session, current_user)
    _require_admin(context)
    try:
        return service.update_policy(
            provider_key,
            enabled=payload.enabled,
            note=payload.note,
            expected_revision=payload.revision,
        )
    except ProviderGovernanceError as exc:
        raise _domain_error(exc) from exc


@router.get("/{provider_key}")
def provider_detail(
    provider_key: str,
    organization_id: Annotated[int, Query(ge=1)],
    session: Session = Depends(session_with_audit_context),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    service, _ = _service(organization_id, session, current_user)
    try:
        return service.detail(provider_key)
    except ProviderGovernanceError as exc:
        raise _domain_error(exc) from exc
