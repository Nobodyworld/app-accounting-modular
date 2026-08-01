"""Bound HTTP request bodies before application routes execute."""

from __future__ import annotations

import logging

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

_ERROR_DETAIL = "Request body exceeds the configured limit."


class RequestBodyLimitMiddleware:
    """Reject request bodies that exceed a configured byte limit.

    The request channel is consumed only until the complete body or the first
    over-limit byte is observed. Accepted messages are replayed to the app, so
    endpoints never execute for a body that is already known to be oversized.
    """

    def __init__(self, app: ASGIApp, *, max_body_bytes: int) -> None:
        if max_body_bytes <= 0:
            raise ValueError("max_body_bytes must be greater than zero")
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = self._content_length(scope)
        if content_length is not None and content_length > self.max_body_bytes:
            await self._reject(scope, send)
            return

        body = bytearray()
        disconnected = False
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                disconnected = True
                break
            if message["type"] != "http.request":
                continue
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.max_body_bytes:
                await self._reject(scope, send)
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break

        replayed = False

        async def replay_receive() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                if disconnected:
                    return {"type": "http.disconnect"}
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return {"type": "http.disconnect"}

        await self.app(scope, replay_receive, send)

    @staticmethod
    def _content_length(scope: Scope) -> int | None:
        for raw_name, raw_value in scope.get("headers", ()):
            if raw_name.lower() != b"content-length":
                continue
            try:
                value = int(raw_value)
            except (TypeError, ValueError):
                return None
            return value if value >= 0 else None
        return None

    async def _reject(self, scope: Scope, send: Send) -> None:
        logger.warning(
            "Rejected oversized request body",
            extra={
                "http_method": scope.get("method"),
                "http_path": scope.get("path"),
                "request_body_limit_bytes": self.max_body_bytes,
            },
        )
        response = JSONResponse(status_code=413, content={"detail": _ERROR_DETAIL})
        await response(scope, _empty_receive, send)


async def _empty_receive() -> Message:
    return {"type": "http.request", "body": b"", "more_body": False}
