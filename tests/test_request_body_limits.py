"""ASGI request-body limit and configuration boundary tests."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from typing import Any

import pytest
from apps.api.config import Settings
from apps.api.limits import MAX_REQUEST_BODY_BYTES
from apps.api.middleware.request_limits import RequestBodyLimitMiddleware
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.types import Message, Scope


def _run_request(
    *,
    chunks: Sequence[bytes],
    limit: int,
    content_length: bytes | None = None,
) -> tuple[list[Message], list[bytes]]:
    downstream_bodies: list[bytes] = []

    async def downstream(scope: Scope, receive: Any, send: Any) -> None:
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] != "http.request":
                break
            body.extend(message.get("body", b""))
            if not message.get("more_body", False):
                break
        downstream_bodies.append(bytes(body))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b'{"ok":true}'})

    headers = [] if content_length is None else [(b"content-length", content_length)]
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/bounded",
        "raw_path": b"/bounded",
        "query_string": b"",
        "headers": headers,
        "client": ("test", 123),
        "server": ("test", 80),
        "root_path": "",
    }
    receive_messages = [
        {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
        for index, chunk in enumerate(chunks)
    ]
    sent: list[Message] = []

    async def receive() -> Message:
        return receive_messages.pop(0)

    async def send(message: Message) -> None:
        sent.append(message)

    asyncio.run(RequestBodyLimitMiddleware(downstream, max_body_bytes=limit)(scope, receive, send))
    return sent, downstream_bodies


def _response(sent: list[Message]) -> tuple[int, dict[str, object]]:
    start = next(message for message in sent if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body")
    return int(start["status"]), json.loads(body)


def test_valid_body_below_limit_reaches_downstream() -> None:
    sent, downstream = _run_request(chunks=[b"valid"], limit=8, content_length=b"5")
    assert _response(sent) == (200, {"ok": True})
    assert downstream == [b"valid"]


def test_body_exactly_at_limit_reaches_downstream() -> None:
    sent, downstream = _run_request(chunks=[b"1234", b"5678"], limit=8, content_length=b"8")
    assert _response(sent)[0] == 200
    assert downstream == [b"12345678"]


def test_over_limit_content_length_is_rejected_without_downstream_execution() -> None:
    sent, downstream = _run_request(chunks=[b"not-read"], limit=8, content_length=b"9")
    assert _response(sent) == (413, {"detail": "Request body exceeds the configured limit."})
    assert downstream == []


def test_over_limit_streamed_body_is_rejected_without_downstream_execution() -> None:
    sent, downstream = _run_request(chunks=[b"1234", b"5678", b"9"], limit=8)
    assert _response(sent)[0] == 413
    assert downstream == []


def test_false_content_length_cannot_bypass_stream_count() -> None:
    sent, downstream = _run_request(chunks=[b"123456789"], limit=8, content_length=b"1")
    assert _response(sent)[0] == 413
    assert downstream == []


def test_sanitized_413_does_not_echo_body_or_headers() -> None:
    secret = b"password=super-secret"
    sent, _ = _run_request(chunks=[secret], limit=4, content_length=str(len(secret)).encode())
    status, payload = _response(sent)
    encoded = json.dumps(payload)
    assert status == 413
    assert payload == {"detail": "Request body exceeds the configured limit."}
    assert "secret" not in encoded
    assert "password" not in encoded


def test_invalid_or_missing_content_length_is_counted_safely() -> None:
    for content_length in (None, b"invalid", b"-1"):
        sent, downstream = _run_request(chunks=[b"123456789"], limit=8, content_length=content_length)
        assert _response(sent)[0] == 413
        assert downstream == []


def test_request_body_setting_defaults_and_allows_only_positive_tighter_overrides() -> None:
    assert Settings().max_request_body_bytes == MAX_REQUEST_BODY_BYTES
    assert Settings.load({"MODACCT_MAX_REQUEST_BODY_BYTES": "1024"}).max_request_body_bytes == 1024
    for invalid in ("0", str(MAX_REQUEST_BODY_BYTES + 1)):
        with pytest.raises(ValidationError):
            Settings.load({"MODACCT_MAX_REQUEST_BODY_BYTES": invalid})


def test_health_and_valid_api_requests_remain_unaffected() -> None:
    app = FastAPI()
    app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=8)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/echo")
    def echo(payload: dict[str, int]) -> dict[str, int]:
        return payload

    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        response = client.post("/echo", content=b'{"n":1}', headers={"content-type": "application/json"})
        assert response.status_code == 200
        assert response.json() == {"n": 1}
