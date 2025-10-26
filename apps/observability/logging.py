"""Structured logging utilities with request correlation support.

The helpers provided by this module focus on production hardening rather than
lightweight debug convenience.  They aim to deliver a single opinionated
logging pipeline that can be reused by every entrypoint (HTTP, background jobs,
and CLI tooling) while remaining compatible with the expectations of Uvicorn
and the standard library logging module.

Key features
============
* Context propagation powered by :mod:`contextvars`, enabling correlation IDs
  and arbitrary metadata to flow through synchronous as well as asynchronous
  code paths.
* JSON and human-readable text formatters that emit deterministic timestamps in
  UTC and gracefully serialise non-standard values.
* Middleware and convenience helpers that enrich ASGI request handling and
  background jobs without relying on framework-specific global state.
* A single ``configure_logging`` entrypoint that normalises Uvicorn loggers to
  avoid double logging while still surfacing access/error events with the same
  formatting pipeline as the rest of the application.
"""

from __future__ import annotations

import json
import logging
import logging.config
import time
from collections.abc import AsyncIterator, Iterable, Iterator, Mapping, MutableMapping
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from starlette.types import ASGIApp

__all__ = [
    "LogFormat",
    "configure_logging",
    "logging_context",
    "async_logging_context",
    "get_context",
    "get_correlation_id",
    "RequestContextMiddleware",
]

LogFormat = Literal["JSON", "TEXT"]

_CONTEXT: ContextVar[Mapping[str, Any] | None] = ContextVar(
    "modacct_logging_context", default=None
)
_CONFIGURED = False

_DEFAULT_INTEGRATED_LOGGERS = (
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
)

_CONTEXT_KEYS = (
    "correlation_id",
    "request_id",
    "request_path",
    "request_method",
)
_RESERVED_ATTRS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
}


class ContextFilter(logging.Filter):
    """Inject contextvars-backed fields into log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - trivial
        context = _CONTEXT.get()
        if context:
            for key, value in context.items():
                setattr(record, key, value)
        for key in _CONTEXT_KEYS:
            if not hasattr(record, key):
                setattr(record, key, None)
        return True


def _json_default(value: object) -> object:
    try:
        return json.JSONEncoder().default(value)
    except TypeError:
        return str(value)


class JsonFormatter(logging.Formatter):
    """Render log records as JSON with consistent metadata."""

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "service": self.service_name,
            "logger": record.name,
            "level": record.levelname,
            "message": record.getMessage(),
        }
        for key in _CONTEXT_KEYS:
            payload[key] = getattr(record, key, None)
        extra = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_ATTRS and key not in _CONTEXT_KEYS
        }
        if extra:
            payload["extra"] = extra
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)
        return json.dumps(payload, default=_json_default)


class TextFormatter(logging.Formatter):
    """Human-readable formatter that preserves context metadata."""

    def __init__(self, service_name: str) -> None:
        template = (
            "%(asctime)s %(levelname)s [%(name)s] "
            f"[{service_name}] "
            "cid=%(correlation_id)s "
            "req=%(request_id)s "
            "%(request_method)s %(request_path)s - "
            "%(message)s"
        )
        super().__init__(template, datefmt="%Y-%m-%dT%H:%M:%SZ")
        # Always format in UTC so that local developer settings do not influence
        # production log output or JSON formatting.
        self.converter = time.gmtime  # type: ignore[assignment]


def get_context() -> dict[str, Any]:
    """Return the current logging context."""

    context = _CONTEXT.get()
    return dict(context) if context else {}


def get_correlation_id() -> str | None:
    """Return the current correlation identifier if set."""

    return get_context().get("correlation_id")


def bind_context(**values: Any) -> Token[Mapping[str, Any] | None]:
    """Merge ``values`` into the current logging context."""

    merged = get_context()
    merged.update(values)
    return _CONTEXT.set(merged)


def reset_context(token: Token[Mapping[str, Any] | None]) -> None:
    """Restore the context associated with ``token``."""

    _CONTEXT.reset(token)


@contextmanager
def logging_context(**values: Any) -> Iterator[None]:
    """Context manager that enriches log records with ``values``."""

    token = bind_context(**values)
    try:
        yield
    finally:
        reset_context(token)


@asynccontextmanager
async def async_logging_context(**values: Any) -> AsyncIterator[None]:
    """Asynchronous variant of :func:`logging_context`.

    This helper prevents repetitive ``try/finally`` boilerplate around ``async``
    code by mirroring the synchronous API and ensuring the context token is
    always restored.
    """

    token = bind_context(**values)
    try:
        yield
    finally:
        reset_context(token)


def configure_logging(
    level: str = "INFO",
    log_format: LogFormat = "JSON",
    *,
    service_name: str = "modular-accounting",
    force: bool = False,
    integrate_uvicorn: bool = True,
    extra_loggers: Iterable[str] | None = None,
) -> None:
    """Initialise application logging with context propagation."""

    global _CONFIGURED
    normalised_format = log_format.upper()
    if normalised_format not in {"JSON", "TEXT"}:
        raise ValueError(
            f"Unsupported log format '{log_format}'. Expected one of: JSON, TEXT."
        )
    if _CONFIGURED and not force:
        return

    formatter_key = "json" if normalised_format == "JSON" else "text"
    formatters = {
        "json": {
            "()": "apps.observability.logging.JsonFormatter",
            "service_name": service_name,
        },
        "text": {
            "()": "apps.observability.logging.TextFormatter",
            "service_name": service_name,
        },
    }

    handler_definition = {
        "class": "logging.StreamHandler",
        "filters": ["context"],
        "formatter": formatter_key,
        "stream": "ext://sys.stdout",
    }

    logger_names: tuple[str, ...]
    if integrate_uvicorn:
        logger_names = _DEFAULT_INTEGRATED_LOGGERS
    else:
        logger_names = tuple()
    if extra_loggers:
        logger_names = (*logger_names, *tuple(extra_loggers))

    logging_config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {"context": {"()": "apps.observability.logging.ContextFilter"}},
        "formatters": formatters,
        "handlers": {"default": handler_definition},
        "root": {"level": level.upper(), "handlers": ["default"]},
    }

    if logger_names:
        logging_config["loggers"] = {
            name: {
                "level": level.upper(),
                "handlers": ["default"],
                "propagate": False,
            }
            for name in logger_names
        }

    logging.config.dictConfig(logging_config)
    logging.captureWarnings(True)
    _CONFIGURED = True


class RequestContextMiddleware:
    """ASGI middleware that assigns correlation IDs to each request."""

    def __init__(self, app: ASGIApp, header_name: str = "x-request-id") -> None:
        self.app = app
        self._header_name = header_name.lower().encode("latin-1")
        self._correlation_header = b"x-correlation-id"

    async def __call__(self, scope: dict[str, Any], receive, send) -> None:  # type: ignore[override]
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        headers: list[tuple[bytes, bytes]] = list(scope.get("headers", []))
        header_lookup = {name.lower(): value for name, value in headers}
        provided_corr = header_lookup.get(self._correlation_header)
        provided_request = header_lookup.get(self._header_name)

        correlation_id = (
            provided_corr or provided_request or str(uuid4()).encode("latin-1")
        )
        if not isinstance(correlation_id, bytes):
            correlation_id = str(correlation_id).encode("latin-1")
        request_id = provided_request or correlation_id

        correlation_str = correlation_id.decode("latin-1")
        request_str = request_id.decode("latin-1")

        state = scope.get("state")
        if state is None:
            scope["state"] = {}
            state = scope["state"]

        if isinstance(state, MutableMapping):
            state.update(
                {
                    "correlation_id": correlation_str,
                    "request_id": request_str,
                }
            )
        else:
            state.correlation_id = correlation_str
            state.request_id = request_str

        token = bind_context(
            correlation_id=correlation_str,
            request_id=request_str,
            request_path=scope.get("path"),
            request_method=scope.get("method"),
        )

        async def send_wrapper(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                existing = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower()
                    not in {self._header_name, self._correlation_header}
                ]
                existing.extend(
                    [
                        (self._header_name, request_id),
                        (self._correlation_header, correlation_id),
                    ]
                )
                message["headers"] = existing
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            reset_context(token)
