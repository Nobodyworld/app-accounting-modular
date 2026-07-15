"""Audit trail read-only routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from ..dependencies import session_with_audit_context
from ..models.models import AuditLog, Membership, Organization, User
from ..schemas import AuditLogSchema
from ..security import get_current_user

router = APIRouter(prefix="/audit", tags=["audit"])


def _require_audit_administrator(session: Session, organization_id: int, current_user: User) -> None:
    """Require active organization membership with administrator privileges."""

    organization = session.get(Organization, organization_id)
    if organization is None or not organization.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    if current_user.id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

    membership = session.exec(
        select(Membership).where(
            Membership.organization_id == organization_id,
            Membership.user_id == current_user.id,
        )
    ).one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized for this organization",
        )
    if not membership.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization administrator access is required",
        )


@router.get("/", response_model=list[AuditLogSchema])
def list_audit_logs(
    organization_id: int = Query(..., ge=1),
    s: Session = Depends(session_with_audit_context),
    current_user: User = Depends(get_current_user),
    entity: str | None = Query(default=None, min_length=1, max_length=255),
    user_id: int | None = Query(default=None, alias="user", ge=1),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    request_id: str | None = Query(default=None, min_length=1, max_length=255),
    limit: int = Query(default=100, ge=1, le=1000),
    after_id: int | None = Query(default=None, ge=1, description="Fetch entries older than this id for pagination"),
) -> list[AuditLogSchema]:
    """Return organization-scoped audit entries to organization administrators."""

    _require_audit_administrator(s, organization_id, current_user)
    if start is not None and end is not None and start > end:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="start must not be after end")

    ts_col = cast(Any, AuditLog.ts)
    id_col = cast(Any, AuditLog.id)
    stmt = (
        select(AuditLog)
        .where(AuditLog.actor_org_id == organization_id)
        .order_by(ts_col.desc())
        .limit(limit)
    )
    if after_id is not None:
        stmt = stmt.where(id_col < after_id)
    if entity:
        stmt = stmt.where(AuditLog.entity_name == entity)
    if user_id is not None:
        stmt = stmt.where(AuditLog.actor_user_id == user_id)
    if request_id:
        stmt = stmt.where(AuditLog.request_id == request_id)
    if start:
        stmt = stmt.where(AuditLog.ts >= start)
    if end:
        stmt = stmt.where(AuditLog.ts <= end)

    logs = s.exec(stmt).all()
    return [AuditLogSchema.model_validate(log) for log in logs]
