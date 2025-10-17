"""Audit logging utilities for Modular Accounting."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlmodel import Session

from .models.models import AuditAction, AuditLog

__all__ = [
    "AuditActor",
    "AuditLogger",
    "get_current_actor",
    "push_actor",
    "pop_actor",
    "use_actor",
    "apply_creation_metadata",
]


@dataclass(slots=True)
class AuditActor:
    """Represents the actor responsible for a change."""

    request_id: str
    user_id: int | None = None
    organization_id: int | None = None
    source: str | None = None
    user_label: str | None = None


_actor_ctx: ContextVar[AuditActor | None] = ContextVar("audit_actor", default=None)


def get_current_actor() -> AuditActor | None:
    """Return the actor currently bound to the context, if any."""

    return _actor_ctx.get()


def push_actor(actor: AuditActor) -> Token:
    """Bind the provided actor to the current context and return a token."""

    return _actor_ctx.set(actor)


def pop_actor(token: Token) -> None:
    """Restore the context to the state before :func:`push_actor`."""

    try:
        _actor_ctx.reset(token)
    except ValueError:
        # When dependencies run in a separate thread (e.g. TestClient thread pool)
        # the context in which the token was created may differ from the context
        # used during teardown. Ignore the reset in this scenario – the worker
        # thread already discarded its context.
        pass


@contextmanager
def use_actor(actor: AuditActor) -> Iterable[AuditActor]:
    """Context manager that sets the active audit actor."""

    token = push_actor(actor)
    try:
        yield actor
    finally:
        pop_actor(token)


def _jsonify(payload: Any) -> Any:
    """Serialise arbitrary payloads into JSON-compatible structures."""

    if payload is None:
        return None
    return jsonable_encoder(payload)


def _compute_diff(
    before: Mapping[str, Any] | None, after: Mapping[str, Any] | None
) -> dict[str, Any] | None:
    """Return a simple diff structure describing key/value changes."""

    if before is None and after is None:
        return None

    before_map = before or {}
    after_map = after or {}

    diff: dict[str, Any] = {}
    for key in sorted(set(before_map) | set(after_map)):
        before_val = before_map.get(key)
        after_val = after_map.get(key)
        if before_val != after_val:
            diff[key] = {"before": before_val, "after": after_val}

    return diff or None


class AuditLogger:
    """Records immutable audit trail entries."""

    def __init__(self, session: Session):
        self.session = session

    def log(
        self,
        action: AuditAction,
        entity_name: str,
        entity_id: str | int | None,
        before: Any = None,
        after: Any = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        """Persist an audit record capturing state transitions."""

        actor = get_current_actor()
        before_json = _jsonify(before)
        after_json = _jsonify(after)
        if isinstance(entity_id, (int, float)):
            entity_id_value: str | None = str(entity_id)
        else:
            entity_id_value = entity_id if entity_id is None else str(entity_id)

        log_entry = AuditLog(
            ts=datetime.utcnow(),
            action=action,
            entity_name=entity_name,
            entity_id=entity_id_value,
            before_state=before_json,
            after_state=after_json,
            payload_diff=_compute_diff(before_json, after_json),
            request_id=(actor.request_id if actor else str(uuid4())),
            actor_user_id=(actor.user_id if actor else None),
            actor_org_id=(actor.organization_id if actor else None),
            actor_label=(actor.user_label if actor else None),
            source=(actor.source if actor else None),
            context=_jsonify(metadata),
        )
        self.session.add(log_entry)
        # Persist immediately to ensure audit entries are durable even if
        # subsequent operations fail.
        self.session.commit()


def apply_creation_metadata(record: Any) -> None:
    """Populate provenance fields on new ORM objects when possible."""

    actor = get_current_actor()
    now = datetime.utcnow()

    if hasattr(record, "created_at") and getattr(record, "created_at") is None:
        setattr(record, "created_at", now)
    if hasattr(record, "updated_at"):
        setattr(record, "updated_at", now)

    if actor is None:
        return

    if hasattr(record, "created_by_id") and getattr(record, "created_by_id", None) is None:
        setattr(record, "created_by_id", actor.user_id)
    if hasattr(record, "updated_by_id"):
        setattr(record, "updated_by_id", actor.user_id)
    if hasattr(record, "organization_id") and getattr(record, "organization_id", None) is None:
        setattr(record, "organization_id", actor.organization_id)
