"""Audit trail read-only routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from ..dependencies import session_with_audit_context
from ..models.models import AuditLog
from ..schemas import AuditLogSchema

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/", response_model=list[AuditLogSchema])
def list_audit_logs(
    s: Session = Depends(session_with_audit_context),
    entity: str | None = Query(default=None),
    user_id: int | None = Query(default=None, alias="user"),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    request_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    after_id: int | None = Query(default=None, description="Fetch entries older than this id for pagination"),
) -> list[AuditLogSchema]:
    """Return audit entries filtered by optional parameters."""
    ts_col = cast(Any, AuditLog.ts)
    id_col = cast(Any, AuditLog.id)
    stmt = select(AuditLog).order_by(ts_col.desc()).limit(limit)
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
