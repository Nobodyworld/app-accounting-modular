"""Audit logging utilities for Modular Accounting."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import UTC, datetime
from queue import Empty, Queue
from threading import Event, Lock, Thread
from typing import Any
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlmodel import Session

# Import audit models
from .models.models import AuditAction, AuditLog

__all__ = [
    "AuditAction",
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


def push_actor(actor: AuditActor) -> Token[AuditActor | None]:
    """Bind the provided actor to the current context and return a token."""

    return _actor_ctx.set(actor)


def pop_actor(token: Token[AuditActor | None]) -> None:
    """Restore the context to the state before :func:`push_actor`."""

    try:
        _actor_ctx.reset(token)
    except ValueError:
        # When dependencies run in a separate thread (e.g. TestClient thread pool)
        # the context in which the token was created may differ from the context
        # used during teardown. Fall back to clearing the actor to avoid leaking
        # context between requests.
        _actor_ctx.set(None)


@contextmanager
def use_actor(actor: AuditActor) -> Iterator[AuditActor]:
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


def _compute_diff(before: Mapping[str, Any] | None, after: Mapping[str, Any] | None) -> dict[str, Any] | None:
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
        self._logger = logging.getLogger(__name__)
        self._queue: Queue[dict[str, Any]] | None = None
        self._worker: Thread | None = None
        self._stop_event: Event | None = None
        self._session_factory: Callable[[], Session] | None = None
        self._worker_init_lock = Lock()

    def log(
        self,
        action: AuditAction,
        entity_name: str,
        entity_id: str | int | None,
        before: Any = None,
        after: Any = None,
        metadata: Mapping[str, Any] | None = None,
        asynchronous: bool = False,
    ) -> None:
        """Persist an audit record capturing state transitions."""

        actor = get_current_actor()
        before_json = _jsonify(before)
        after_json = _jsonify(after)
        if isinstance(entity_id, (int, float)):
            entity_id_value: str | None = str(entity_id)
        else:
            entity_id_value = entity_id if entity_id is None else str(entity_id)

        diff = _compute_diff(before_json, after_json)
        payload: dict[str, Any] = {
            "ts": datetime.now(UTC),
            "action": action,
            "entity_name": entity_name,
            "entity_id": entity_id_value,
            "before_state": before_json,
            "after_state": after_json,
            "payload_diff": diff,
            "request_id": (actor.request_id if actor else str(uuid4())),
            "actor_user_id": (actor.user_id if actor else None),
            "actor_org_id": (actor.organization_id if actor else None),
            "actor_label": (actor.user_label if actor else None),
            "source": (actor.source if actor else None),
            "context": _jsonify(metadata),
        }

        if asynchronous:
            self._enqueue(payload)
            return

        log_entry = AuditLog(**payload)
        self.session.add(log_entry)
        self.session.commit()

    def _ensure_async_worker(self) -> None:
        """Initialise the background worker if asynchronous logging is requested."""

        with self._worker_init_lock:
            if self._queue is not None:
                return

            bind = self.session.get_bind()
            engine = getattr(bind, "engine", bind)

            self._queue = Queue()
            self._stop_event = Event()
            self._session_factory = lambda: Session(engine)
            self._worker = Thread(target=self._worker_loop, name="audit-flusher", daemon=True)
            self._worker.start()

    def _enqueue(self, payload: dict[str, Any]) -> None:
        """Queue audit payloads for background persistence."""

        self._ensure_async_worker()
        assert self._queue is not None  # for mypy
        self._queue.put(payload)

    def _worker_loop(self) -> None:
        """Continuously flush audit records from the queue."""

        assert self._queue is not None
        assert self._session_factory is not None
        assert self._stop_event is not None

        while not self._stop_event.is_set() or not self._queue.empty():
            try:
                payload = self._queue.get(timeout=0.25)
            except Empty:
                continue

            try:
                with self._session_factory() as session:
                    session.add(AuditLog(**payload))
                    session.commit()
            except Exception as exc:  # pragma: no cover - defensive logging path
                self._logger.warning("Failed to flush audit log entry", exc_info=exc)
            finally:
                self._queue.task_done()

    def flush(self, *, wait: bool = True, timeout: float | None = None) -> None:
        """Flush buffered audit entries when asynchronous logging is used."""

        if self._queue is None:
            return
        if not wait:
            return
        self._queue.join()

    def close(self) -> None:
        """Terminate the background worker after flushing outstanding entries."""

        if self._stop_event is None or self._queue is None:
            return
        self._stop_event.set()
        self._queue.join()
        if self._worker is not None:
            self._worker.join(timeout=1)

    def __del__(self) -> None:  # pragma: no cover - best-effort cleanup
        try:
            self.close()
        except Exception:
            pass


def apply_creation_metadata(record: Any) -> None:
    """Populate provenance fields on new ORM objects when possible."""

    actor = get_current_actor()
    now = datetime.now(UTC)

    if hasattr(record, "created_at"):
        if getattr(record, "created_at", None) is None:
            record.created_at = now
    if hasattr(record, "updated_at"):
        record.updated_at = now

    if actor is None:
        return

    if hasattr(record, "created_by_id"):
        if getattr(record, "created_by_id", None) is None:
            record.created_by_id = actor.user_id
    if hasattr(record, "updated_by_id"):
        record.updated_by_id = actor.user_id
    if hasattr(record, "organization_id"):
        if getattr(record, "organization_id", None) is None:
            record.organization_id = actor.organization_id
