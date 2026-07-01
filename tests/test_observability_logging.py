"""Observability logging tests ensuring formatters and context utilities behave."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import pytest
from apps.observability.logging import (
    ContextFilter,
    JsonFormatter,
    RequestContextMiddleware,
    TextFormatter,
    async_logging_context,
    configure_logging,
    get_context,
    logging_context,
)
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient


def _multiprocessing_log_worker(queue: Any) -> None:
    configure_logging("INFO", "JSON", service_name="svc-mp", force=True)
    with logging_context(correlation_id="cid-child"):
        logger = logging.getLogger("tests.multiproc")
        logger.info("child log")
        handlers = logger.handlers or logging.getLogger().handlers
        if not handlers:
            return
        handler = handlers[0]
        record = logging.LogRecord(
            name="tests.multiproc",
            level=logging.INFO,
            pathname=__file__,
            lineno=0,
            msg="child log",
            args=(),
            exc_info=None,
        )
        ContextFilter().filter(record)
        queue.put(handler.format(record))


def test_logging_context_injects_fields() -> None:
    with logging_context(correlation_id="cid-123", request_id="req-456", tenant="demo"):
        record = logging.LogRecord(
            name="tests.logging",
            level=logging.INFO,
            pathname=__file__,
            lineno=0,
            msg="context propagation works",
            args=(),
            exc_info=None,
        )
        ContextFilter().filter(record)

    assert record.correlation_id == "cid-123"
    assert record.request_id == "req-456"
    assert hasattr(record, "tenant")
    assert record.tenant == "demo"


def test_json_formatter_outputs_expected_structure() -> None:
    formatter = JsonFormatter(service_name="svc")
    record = logging.LogRecord(
        name="tests.json", level=logging.INFO, pathname=__file__, lineno=0, msg="hello", args=(), exc_info=None
    )
    record.correlation_id = "corr-1"
    record.request_id = "req-1"
    payload = json.loads(formatter.format(record))
    assert payload["service"] == "svc"
    assert payload["message"] == "hello"
    assert payload["correlation_id"] == "corr-1"
    assert payload["request_id"] == "req-1"


def test_text_formatter_renders_utc_timestamp() -> None:
    formatter = TextFormatter(service_name="svc")
    record = logging.LogRecord(
        name="tests.text", level=logging.INFO, pathname=__file__, lineno=0, msg="hello", args=(), exc_info=None
    )
    record.correlation_id = "corr-1"
    record.request_id = "req-1"
    ContextFilter().filter(record)
    formatted = formatter.format(record)
    # Ensure the timestamp suffix uses ``Z`` (UTC) and the contextual fields are embedded.
    assert formatted.startswith("20")
    assert "corr-1" in formatted
    assert "Z " in formatted
    assert "hello" in formatted


def test_async_logging_context_propagates_values() -> None:
    async def runner() -> None:
        async with async_logging_context(correlation_id="cid-async"):
            record = logging.LogRecord(
                name="tests.async", level=logging.INFO, pathname=__file__, lineno=0, msg="async", args=(), exc_info=None
            )
            ContextFilter().filter(record)
        assert record.correlation_id == "cid-async"

    asyncio.run(runner())


def test_configure_logging_enriches_uvicorn_loggers(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", "JSON", service_name="svc", force=True)

    with logging_context(correlation_id="cid-uvicorn"):
        logging.getLogger("uvicorn.access").info("uvicorn-log")

    stdout = capsys.readouterr().out.strip().splitlines()
    assert stdout, "Expected log output from uvicorn logger"
    payload = json.loads(stdout[-1])
    assert payload["correlation_id"] == "cid-uvicorn"
    uvicorn_logger = logging.getLogger("uvicorn.access")
    assert uvicorn_logger.handlers, "Expected uvicorn logger to share the configured handler"
    assert any(isinstance(flt, ContextFilter) for handler in uvicorn_logger.handlers for flt in handler.filters)


def test_request_context_middleware_assigns_request_ids() -> None:
    configure_logging("INFO", "TEXT", service_name="test-api", force=True)
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/ping")
    async def ping(request: Request) -> JSONResponse:  # pragma: no cover - exercised via TestClient
        context = get_context()
        logging.getLogger("tests.middleware").info("handling request")
        context["state_correlation"] = request.state.correlation_id
        context["state_request_id"] = request.state.request_id
        return JSONResponse(context)

    client = TestClient(app)

    response = client.get("/ping", headers={"x-correlation-id": "abc123"})
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    assert body["correlation_id"] == "abc123"
    assert body["request_id"] == "abc123"
    assert response.headers["x-request-id"] == "abc123"
    assert response.headers["x-correlation-id"] == "abc123"
    assert body["state_correlation"] == "abc123"
    assert body["state_request_id"] == "abc123"

    second = client.get("/ping")
    assert second.status_code == 200
    auto_body: dict[str, Any] = second.json()
    assert auto_body["correlation_id"] == auto_body["request_id"]
    assert second.headers["x-request-id"] == auto_body["request_id"]
    assert second.headers["x-correlation-id"] == auto_body["correlation_id"]
    assert auto_body["correlation_id"] != body["correlation_id"]
    assert auto_body["state_correlation"] == auto_body["correlation_id"]
    assert auto_body["state_request_id"] == auto_body["request_id"]


# TODO - (logging) Validate structured logging under multiprocessing executors.
def test_logging_context_survives_multiprocessing(tmp_path) -> None:
    """Ensure child processes can emit logs with contextual fields."""
    configure_logging("INFO", "JSON", service_name="svc-mp", force=True)

    import multiprocessing as mp

    queue: mp.Queue[str] = mp.Queue()
    proc = mp.Process(target=_multiprocessing_log_worker, args=(queue,))
    proc.start()
    proc.join(timeout=60)
    if proc.is_alive():
        proc.terminate()
        proc.join(timeout=10)
        pytest.fail("multiprocessing logging worker timed out")
    assert proc.exitcode == 0
    output = queue.get(timeout=15)
    payload = json.loads(output)
    assert payload["correlation_id"] == "cid-child"
    assert payload["message"] == "child log"
