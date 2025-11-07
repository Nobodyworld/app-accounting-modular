"""Shared FastAPI dependencies."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from uuid import uuid4

from fastapi import Depends, Header
from sqlmodel import Session

from .audit import AuditActor, use_actor
from .db import get_session

logger = logging.getLogger(__name__)


def _parse_optional_int(value: str | None) -> int | None:
    """Safely coerce a header value into an integer identifier."""

    if value is None:
        return None
    try:
        return int(value)
    except ValueError:  # pragma: no cover - defensive
        logger.warning("invalid identifier header", extra={"value": value})
        # TODO - Emit structured metrics for malformed identifier headers.
        return None


def session_with_audit_context(
    s: Session = Depends(get_session),
    x_request_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_org_id: str | None = Header(default=None),
    x_user_label: str | None = Header(default=None),
) -> Iterator[Session]:
    """Yield a database session while seeding the audit actor context."""

    actor = AuditActor(
        request_id=x_request_id or str(uuid4()),
        user_id=_parse_optional_int(x_user_id),
        organization_id=_parse_optional_int(x_org_id),
        source="api",
        user_label=x_user_label,
    )
    # TODO - Validate header provenance to prevent spoofed audit metadata.
    # TODO - (security) Bind actor context to auth session identifiers for replay protection.
    with use_actor(actor):
        yield s
