"""Lightweight tracing primitives with optional OpenTelemetry compatibility."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import ExitStack, asynccontextmanager, contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.middleware.base import RequestResponseEndpoint
from starlette.types import ASGIApp

__all__ = [
    "TracingConfig",
    "configure_tracing",
    "is_tracing_enabled",
    "get_tracing_config",
    "current_span_ids",
    "traced",
    "atraced",
    "RequestTraceMiddleware",
]


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TracingConfig:
    """Configuration describing the active tracing exporter."""

    service_name: str
    exporter: str
    enabled: bool = True
    otel_enabled: bool = False
    endpoint: str | None = None


@dataclass(slots=True)
class SpanContext:
    """Runtime metadata describing a span instance."""

    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    start_time: float = field(default_factory=time.perf_counter)
    end_time: float | None = None

    def finish(self) -> None:
        """Mark the span as completed and emit it via the exporter."""

        self.end_time = time.perf_counter()
        _export_span(self)


_CONFIG: TracingConfig | None = None
_CURRENT_SPAN: ContextVar[SpanContext | None] = ContextVar("modacct_current_span", default=None)
_OTEL_TRACER: Any | None = None


def _noop_exporter(_: SpanContext) -> None:
    """Default exporter used when tracing backends are unavailable."""

    return None


_EXPORTER: Callable[[SpanContext], None] = _noop_exporter


def _generate_trace_id() -> str:
    return uuid4().hex


def _generate_span_id() -> str:
    return uuid4().hex[:16]


def _format_traceparent(trace_id: str, span_id: str) -> str:
    """Return a W3C traceparent header for the provided identifiers."""

    normalised_trace = trace_id.zfill(32)[:32]
    normalised_span = span_id.zfill(16)[:16]
    return f"00-{normalised_trace}-{normalised_span}-01"


def _parse_traceparent(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    parts = value.split("-", 3)
    if len(parts) != 4:
        return None, None
    trace_id, span_id = parts[1], parts[2]
    if len(trace_id) != 32 or len(span_id) != 16:
        return None, None
    return trace_id, span_id


def _export_span(span: SpanContext) -> None:
    try:
        _EXPORTER(span)
    except Exception:  # pragma: no cover - defensive logging
        logger.exception("Tracing exporter failed", extra={"span": span})


def configure_tracing(
    service_name: str,
    *,
    exporter: str = "console",
    endpoint: str | None = None,
) -> TracingConfig:
    """Configure tracing for the current process.

    The implementation prefers OpenTelemetry when available but gracefully
    falls back to an in-process span exporter that logs completed spans. When
    ``exporter`` is set to ``"disabled"`` tracing context is not generated.
    """

    global _CONFIG, _OTEL_TRACER, _EXPORTER

    exporter = exporter.lower()
    if exporter == "disabled":
        _CONFIG = TracingConfig(service_name=service_name, exporter=exporter, enabled=False)
        _OTEL_TRACER = None
        _EXPORTER = _noop_exporter
        logger.info("Tracing disabled via configuration.")
        return _CONFIG

    otel_enabled = False
    otel_endpoint: str | None = endpoint

    try:  # pragma: no cover - exercised when OpenTelemetry is installed
        from opentelemetry import trace  # type: ignore[import-not-found]
        from opentelemetry.sdk.resources import Resource  # type: ignore[import-not-found]
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-not-found]
        from opentelemetry.sdk.trace.export import (  # type: ignore[import-not-found]
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )

        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        if exporter == "otlp":
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore[import-not-found]
                    OTLPSpanExporter,
                )

                otlp_kwargs = {"endpoint": otel_endpoint} if otel_endpoint else {}
                provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(**otlp_kwargs)))
            except Exception as exc:  # pragma: no cover - optional dependency
                logger.warning(
                    "OTLP exporter unavailable; falling back to console spans.",
                    extra={"error": str(exc)},
                )
                provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        else:
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

        trace.set_tracer_provider(provider)
        _OTEL_TRACER = trace.get_tracer(service_name)
        otel_enabled = True
        _EXPORTER = _noop_exporter
        logger.info("Configured OpenTelemetry tracer", extra={"exporter": exporter})
    except Exception:  # pragma: no cover - default fallback path
        _OTEL_TRACER = None

        if exporter == "otlp":
            logger.warning(
                ("OpenTelemetry not installed; OTLP exporter downgraded to " "console logging."),
            )

        def _log_export(span: SpanContext) -> None:
            duration = span.end_time - span.start_time if span.end_time is not None else None
            logger.info(
                "Span completed",
                extra={
                    "trace_id": span.trace_id,
                    "span_id": span.span_id,
                    "parent_span_id": span.parent_span_id,
                    "duration": duration,
                    "attributes": span.attributes,
                },
            )

        _EXPORTER = _log_export

    _CONFIG = TracingConfig(
        service_name=service_name,
        exporter=exporter,
        enabled=True,
        otel_enabled=otel_enabled,
        endpoint=endpoint,
    )
    return _CONFIG


def is_tracing_enabled() -> bool:
    """Return ``True`` when tracing context should be generated."""

    return bool(_CONFIG and _CONFIG.enabled)


def get_tracing_config() -> TracingConfig | None:
    """Return the current tracing configuration if initialised."""

    return _CONFIG


def current_span_ids() -> tuple[str | None, str | None]:
    """Return the active trace/span identifiers if any."""

    span = _CURRENT_SPAN.get()
    if span is None:
        return None, None
    return span.trace_id, span.span_id


@contextmanager
def _otel_span(name: str, attributes: dict[str, Any]) -> Iterator[Any | None]:
    if _OTEL_TRACER is None:
        yield None
        return

    cm = _OTEL_TRACER.start_as_current_span(name)
    with cm as span:
        for key, value in attributes.items():
            try:
                span.set_attribute(key, value)
            except Exception:  # pragma: no cover - defensive attribute casting
                span.set_attribute(key, str(value))

        ctx = span.get_span_context()
        trace_id = f"{ctx.trace_id:032x}"
        span_id = f"{ctx.span_id:016x}"
        stack = ExitStack()
        from apps.observability.logging import logging_context

        stack.enter_context(logging_context(trace_id=trace_id, span_id=span_id))
        token = _CURRENT_SPAN.set(SpanContext(trace_id=trace_id, span_id=span_id, parent_span_id=None))
        try:
            yield span
        finally:
            stack.close()
            _CURRENT_SPAN.reset(token)


@contextmanager
def traced(
    name: str,
    *,
    trace_id: str | None = None,
    parent_span_id: str | None = None,
    **attributes: Any,
) -> Iterator[Any | SpanContext | None]:
    """Context manager that instruments a block of code as a span."""

    if not is_tracing_enabled():
        yield None
        return

    if _OTEL_TRACER is not None:
        with _otel_span(name, attributes) as span:
            yield span
        return

    parent = _CURRENT_SPAN.get()
    resolved_trace_id = trace_id or (parent.trace_id if parent else _generate_trace_id())
    resolved_parent = parent_span_id or (parent.span_id if parent else None)
    span_id = _generate_span_id()
    context = SpanContext(
        trace_id=resolved_trace_id,
        span_id=span_id,
        parent_span_id=resolved_parent,
        attributes=dict(attributes),
    )
    token: Token[SpanContext | None] = _CURRENT_SPAN.set(context)
    from apps.observability.logging import logging_context

    with ExitStack() as stack:
        stack.enter_context(logging_context(trace_id=context.trace_id, span_id=context.span_id))
        try:
            yield context
        finally:
            context.finish()
            _CURRENT_SPAN.reset(token)


@asynccontextmanager
async def atraced(
    name: str,
    *,
    trace_id: str | None = None,
    parent_span_id: str | None = None,
    **attributes: Any,
) -> AsyncIterator[Any | SpanContext | None]:
    """Async variant of :func:`traced`."""

    with traced(
        name,
        trace_id=trace_id,
        parent_span_id=parent_span_id,
        **attributes,
    ) as span:
        yield span


class RequestTraceMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that wraps requests in tracing spans."""

    def __init__(self, app: ASGIApp, *, operation_name: str | None = None) -> None:
        super().__init__(app)
        self._operation_name = operation_name

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if not is_tracing_enabled():
            return await call_next(request)

        parent_trace, parent_span = _parse_traceparent(request.headers.get("traceparent"))
        name = self._operation_name or f"HTTP {request.method}"
        async with atraced(
            name,
            trace_id=parent_trace,
            parent_span_id=parent_span,
            http_method=request.method,
            http_path=request.url.path,
        ) as span:
            response = await call_next(request)
            if span is not None:
                if isinstance(span, SpanContext):
                    span.attributes.setdefault("http_status", response.status_code)
                else:  # OpenTelemetry span
                    try:
                        span.set_attribute("http.status_code", response.status_code)
                    except Exception:  # pragma: no cover - defensive
                        logger.debug("Unable to annotate OpenTelemetry span")

                trace_id, span_id = current_span_ids()
                if trace_id and span_id:
                    response.headers["traceparent"] = _format_traceparent(trace_id, span_id)

            return response
