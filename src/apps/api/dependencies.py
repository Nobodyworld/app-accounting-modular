"""Shared FastAPI dependencies."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from uuid import uuid4

from fastapi import Depends, Header
from prometheus_client import Counter
from sqlmodel import Session

from apps.observability.metrics import metrics_registry

from .audit import AuditActor, use_actor
from .db import get_session
from .security import _decode_token

logger = logging.getLogger(__name__)
_malformed_header_counter = metrics_registry.header_malformed_total
_spoofed_header_counter = Counter(
    "modacct_header_spoof_total",
    "Count of rejected header provenance checks.",
    labelnames=("reason",),
    registry=metrics_registry.registry,
)


def _parse_optional_int(value: str | None) -> int | None:
    """Safely coerce a header value into an integer identifier."""

    if value is None:
        return None
    try:
        return int(value)
    except ValueError:  # pragma: no cover - defensive
        logger.warning("invalid identifier header", extra={"value": value})
        _malformed_header_counter.labels(header="id").inc()
        return None


def session_with_audit_context(
    s: Session = Depends(get_session),
    x_request_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_org_id: str | None = Header(default=None),
    x_user_label: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> Iterator[Session]:
    """Yield a database session while seeding the audit actor context."""

    session_id = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
        try:
            payload = _decode_token(token)
            session_id = payload.get("sid")
        except Exception:  # pragma: no cover - invalid tokens handled upstream
            session_id = None

    if x_user_id and not x_org_id:
        _spoofed_header_counter.labels(reason="missing-org").inc()
        logger.warning("Missing org header for user-scoped request", extra={"user_header": x_user_id})
    if x_org_id and not x_user_id:
        _spoofed_header_counter.labels(reason="missing-user").inc()
        logger.warning("Missing user header for org-scoped request", extra={"org_header": x_org_id})

    actor = AuditActor(
        request_id=session_id or x_request_id or str(uuid4()),
        user_id=_parse_optional_int(x_user_id),
        organization_id=_parse_optional_int(x_org_id),
        source=session_id or "api",
        user_label=x_user_label,
    )
    # TODO - Validate header provenance to prevent spoofed audit metadata.
    # TODO - (security) Bind actor context to auth session identifiers for replay protection.
    with use_actor(actor):
        yield s
