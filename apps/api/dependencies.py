"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Optional
from uuid import uuid4

from fastapi import Depends, Header
from sqlmodel import Session

from .audit import AuditActor, use_actor
from .db import get_session


def _parse_optional_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:  # pragma: no cover - defensive
        return None


def session_with_audit_context(
    s: Session = Depends(get_session),
    x_request_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_org_id: str | None = Header(default=None),
    x_user_label: str | None = Header(default=None),
) -> Iterator[Session]:
    actor = AuditActor(
        request_id=x_request_id or str(uuid4()),
        user_id=_parse_optional_int(x_user_id),
        organization_id=_parse_optional_int(x_org_id),
        source="api",
        user_label=x_user_label,
    )
    with use_actor(actor):
        yield s
