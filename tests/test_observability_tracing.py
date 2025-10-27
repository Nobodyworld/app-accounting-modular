"""Tests covering the lightweight tracing instrumentation."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.observability.logging import get_context
from apps.observability.tracing import (
    RequestTraceMiddleware,
    configure_tracing,
    current_span_ids,
    traced,
)


def test_traced_context_populates_logging_context() -> None:
    configure_tracing("test-suite", exporter="console")

    with traced("unit-test", component="spec") as span:
        trace_id, span_id = current_span_ids()
        context = get_context()

        assert trace_id is not None
        assert span_id is not None
        assert context.get("trace_id") == trace_id
        assert context.get("span_id") == span_id
        assert span is not None

        if hasattr(span, "attributes"):
            assert span.attributes.get("component") == "spec"


def test_request_trace_middleware_sets_traceparent_header() -> None:
    configure_tracing("middleware", exporter="console")

    app = FastAPI()
    app.add_middleware(RequestTraceMiddleware)

    @app.get("/ping")
    async def ping() -> dict[str, str | None]:  # pragma: no cover - executed via client
        context = get_context()
        return {"trace": context.get("trace_id")}

    client = TestClient(app)

    response = client.get("/ping")

    assert response.status_code == 200
    assert response.headers.get("traceparent") is not None
    assert response.json()["trace"] is not None


def test_request_trace_middleware_respects_incoming_traceparent() -> None:
    configure_tracing("middleware", exporter="console")

    app = FastAPI()
    app.add_middleware(RequestTraceMiddleware)

    @app.get("/trace")
    async def trace() -> dict[str, str | None]:  # pragma: no cover - executed via client
        trace_id, _ = current_span_ids()
        return {"trace": trace_id}

    client = TestClient(app)
    incoming = "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"
    response = client.get("/trace", headers={"traceparent": incoming})

    assert response.status_code == 200
    body = response.json()
    assert body["trace"] is not None
    assert body["trace"].startswith("0123456789abcdef0123456789abcdef")
