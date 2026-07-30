"""Shared outbound-provider trust-boundary controls."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Mapping
from typing import Any, NoReturn

import requests

MAX_PROVIDER_RESPONSE_BYTES = 1 * 1024 * 1024
MAX_FX_RATE_RECORDS = 512
MAX_MARKET_PRICE_RECORDS = 10_000
MAX_MARKET_REQUEST_DAYS = 10_000

PROVIDER_CONNECT_TIMEOUT_SECONDS = 5
PROVIDER_READ_TIMEOUT_SECONDS = 20
MAX_PROVIDER_ATTEMPTS = 2
PROVIDER_READ_CHUNK_BYTES = 64 * 1024
PROVIDER_RETRY_BACKOFF_SECONDS = 0.05

_TRANSIENT_HTTP_STATUSES = frozenset({429, 502, 503, 504})
_ERROR_MESSAGE = {
    "request": "Provider request parameters are invalid",
    "transport": "Provider request failed",
    "limit": "Provider response exceeded the configured limit",
    "payload": "Provider returned an invalid payload",
}

logger = logging.getLogger(__name__)


class ProviderBoundaryError(RuntimeError):
    """Base class for sanitized outbound-provider failures."""


class ProviderRequestError(ProviderBoundaryError):
    """The application rejected provider request parameters before network I/O."""


class ProviderTransportError(ProviderBoundaryError):
    """The provider request failed at the network or HTTP-status boundary."""


class ProviderResponseLimitError(ProviderBoundaryError):
    """The provider response exceeded an application byte or record limit."""


class ProviderPayloadError(ProviderBoundaryError):
    """The provider returned malformed or structurally invalid data."""


class _TransientHTTPStatus(Exception):
    pass


class _NonRetryableHTTPStatus(Exception):
    pass


def _raise_limit() -> NoReturn:
    raise ProviderResponseLimitError(_ERROR_MESSAGE["limit"])


def _log_failure(*, provider_key: str, operation: str, attempt: int, classification: str) -> None:
    logger.warning(
        "Outbound provider request rejected",
        extra={
            "provider": provider_key,
            "operation": operation,
            "attempt": attempt,
            "failure_classification": classification,
            "byte_limit": MAX_PROVIDER_RESPONSE_BYTES,
        },
    )


def _read_bounded_response(response: requests.Response, *, max_bytes: int) -> Mapping[str, Any]:
    try:
        status_code = response.status_code
        if status_code in _TRANSIENT_HTTP_STATUSES:
            raise _TransientHTTPStatus
        if status_code >= 400:
            raise _NonRetryableHTTPStatus

        declared_length = response.headers.get("Content-Length")
        if declared_length is not None:
            try:
                parsed_length = int(declared_length)
            except (TypeError, ValueError):
                parsed_length = -1
            if parsed_length > max_bytes:
                _raise_limit()

        body = bytearray()
        for chunk in response.iter_content(chunk_size=PROVIDER_READ_CHUNK_BYTES):
            if not chunk:
                continue
            remaining = max_bytes + 1 - len(body)
            body.extend(chunk[:remaining])
            if len(body) > max_bytes:
                _raise_limit()

        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderPayloadError(_ERROR_MESSAGE["payload"]) from exc
        if not isinstance(payload, Mapping):
            raise ProviderPayloadError(_ERROR_MESSAGE["payload"])
        return payload
    finally:
        response.close()


def get_bounded_json(
    url: str,
    *,
    provider_key: str,
    operation: str,
    params: Mapping[str, str] | None = None,
    request_get: Callable[..., requests.Response] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    max_bytes: int = MAX_PROVIDER_RESPONSE_BYTES,
    max_attempts: int = MAX_PROVIDER_ATTEMPTS,
) -> Mapping[str, Any]:
    """Fetch one HTTPS JSON mapping with bounded bytes, retries, and diagnostics."""

    if not url.startswith("https://"):
        raise ProviderRequestError(_ERROR_MESSAGE["request"])
    if max_bytes < 1 or max_bytes > MAX_PROVIDER_RESPONSE_BYTES:
        raise ProviderRequestError(_ERROR_MESSAGE["request"])
    if max_attempts < 1 or max_attempts > MAX_PROVIDER_ATTEMPTS:
        raise ProviderRequestError(_ERROR_MESSAGE["request"])

    get = request_get or requests.get
    for attempt in range(1, max_attempts + 1):
        try:
            response = get(
                url,
                params=dict(params) if params is not None else None,
                timeout=(PROVIDER_CONNECT_TIMEOUT_SECONDS, PROVIDER_READ_TIMEOUT_SECONDS),
                stream=True,
            )
            return _read_bounded_response(response, max_bytes=max_bytes)
        except ProviderResponseLimitError:
            _log_failure(
                provider_key=provider_key,
                operation=operation,
                attempt=attempt,
                classification="response-limit",
            )
            raise
        except ProviderPayloadError:
            _log_failure(
                provider_key=provider_key,
                operation=operation,
                attempt=attempt,
                classification="invalid-payload",
            )
            raise
        except _NonRetryableHTTPStatus as exc:
            _log_failure(
                provider_key=provider_key,
                operation=operation,
                attempt=attempt,
                classification="http-status",
            )
            raise ProviderTransportError(_ERROR_MESSAGE["transport"]) from exc
        except (_TransientHTTPStatus, requests.ConnectionError, requests.Timeout) as exc:
            _log_failure(
                provider_key=provider_key,
                operation=operation,
                attempt=attempt,
                classification="transient",
            )
            if attempt == max_attempts:
                raise ProviderTransportError(_ERROR_MESSAGE["transport"]) from exc
            sleep(PROVIDER_RETRY_BACKOFF_SECONDS)
        except requests.RequestException as exc:
            _log_failure(
                provider_key=provider_key,
                operation=operation,
                attempt=attempt,
                classification="transport",
            )
            raise ProviderTransportError(_ERROR_MESSAGE["transport"]) from exc

    raise ProviderTransportError(_ERROR_MESSAGE["transport"])  # pragma: no cover
