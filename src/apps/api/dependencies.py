"""Shared FastAPI dependencies."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from uuid import uuid4

from fastapi import Depends, Header, HTTPException, status
from prometheus_client import Counter
from sqlmodel import Session

from apps.observability.metrics import metrics_registry

from .audit import AuditActor, use_actor
from .db import get_session
from .models.models import User
from .security import get_current_user

logger = logging.getLogger(__name__)
_malformed_header_counter = metrics_registry.header_malformed_total
_spoofed_header_counter = Counter(
    "modacct_header_spoof_total",
    "Count of rejected header provenance checks.",
    labelnames=("reason",),
    registry=metrics_registry.registry,
)
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _trusted_request_id(value: str | None) -> str:
    """Return a bounded correlation identifier or a generated request UUID."""

    if value is None:
        return str(uuid4())
    candidate = value.strip()
    if candidate and _REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    _malformed_header_counter.labels(header="request-id").inc()
    logger.warning("Rejected malformed request-id header")
    return str(uuid4())


def _reject_client_identity_headers(
    *,
    x_user_id: str | None,
    x_org_id: str | None,
    x_user_label: str | None,
) -> None:
    """Reject public headers that attempt to provide audit identity."""

    supplied = [
        name
        for name, value in (
            ("x-user-id", x_user_id),
            ("x-org-id", x_org_id),
            ("x-user-label", x_user_label),
        )
        if value is not None
    ]
    if not supplied:
        return
    _spoofed_header_counter.labels(reason="client-identity-header").inc()
    logger.warning("Rejected client-supplied audit identity headers", extra={"headers": supplied})
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Client-supplied audit identity headers are not allowed",
    )


def authenticated_audit_context(
    current_user: User = Depends(get_current_user),
    x_request_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_org_id: str | None = Header(default=None),
    x_user_label: str | None = Header(default=None),
) -> Iterator[None]:
    """Bind a trusted request actor derived from the authenticated principal."""

    _reject_client_identity_headers(
        x_user_id=x_user_id,
        x_org_id=x_org_id,
        x_user_label=x_user_label,
    )
    if current_user.id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

    actor = AuditActor(
        request_id=_trusted_request_id(x_request_id),
        user_id=current_user.id,
        organization_id=None,
        source="api",
        user_label=current_user.email,
    )
    with use_actor(actor):
        yield


def session_with_audit_context(
    s: Session = Depends(get_session),
    _actor_context: None = Depends(authenticated_audit_context),
) -> Iterator[Session]:
    """Yield a database session under the protected router audit context."""

    yield s
