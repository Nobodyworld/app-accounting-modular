from __future__ import annotations

import logging
from collections.abc import Iterable

import pytest
import requests
from plugins.provider_limits import (
    PROVIDER_CONNECT_TIMEOUT_SECONDS,
    PROVIDER_READ_CHUNK_BYTES,
    PROVIDER_READ_TIMEOUT_SECONDS,
    ProviderPayloadError,
    ProviderResponseLimitError,
    ProviderTransportError,
    get_bounded_json,
)


class StubResponse:
    def __init__(
        self,
        body: bytes = b"{}",
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        chunks: Iterable[bytes] | None = None,
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self._chunks = list(chunks) if chunks is not None else [body]
        self.closed = False
        self.iterated = False

    def iter_content(self, *, chunk_size: int) -> Iterable[bytes]:
        assert chunk_size == PROVIDER_READ_CHUNK_BYTES
        self.iterated = True
        yield from self._chunks

    def close(self) -> None:
        self.closed = True


def _fetch(
    response_or_error: StubResponse | Exception,
    *,
    max_bytes: int = 32,
) -> tuple[object, list[dict[str, object]]]:
    calls: list[dict[str, object]] = []

    def get(url: str, **kwargs: object) -> requests.Response:
        calls.append({"url": url, **kwargs})
        if isinstance(response_or_error, Exception):
            raise response_or_error
        return response_or_error  # type: ignore[return-value]

    result = get_bounded_json(
        "https://provider.invalid/data",
        provider_key="test-provider",
        operation="test-operation",
        request_get=get,
        max_bytes=max_bytes,
    )
    return result, calls


def test_normal_body_below_limit_uses_streaming_and_split_timeouts() -> None:
    response = StubResponse(b'{"ok":true}')
    result, calls = _fetch(response)

    assert result == {"ok": True}
    assert calls == [
        {
            "url": "https://provider.invalid/data",
            "params": None,
            "timeout": (PROVIDER_CONNECT_TIMEOUT_SECONDS, PROVIDER_READ_TIMEOUT_SECONDS),
            "stream": True,
        }
    ]
    assert response.iterated
    assert response.closed


def test_body_exactly_at_limit_is_accepted() -> None:
    response = StubResponse(b"{}")
    result, _ = _fetch(response, max_bytes=2)

    assert result == {}
    assert response.closed


def test_declared_content_length_above_limit_is_rejected_before_iteration() -> None:
    response = StubResponse(b"{}", headers={"Content-Length": "3"})

    with pytest.raises(ProviderResponseLimitError):
        _fetch(response, max_bytes=2)

    assert not response.iterated
    assert response.closed


@pytest.mark.parametrize("headers", [{}, {"Content-Length": "1"}])
def test_streamed_body_above_limit_catches_missing_or_false_length(
    headers: dict[str, str],
) -> None:
    response = StubResponse(headers=headers, chunks=[b"{", b"}", b"x"])

    with pytest.raises(ProviderResponseLimitError):
        _fetch(response, max_bytes=2)

    assert response.closed


def test_accumulator_never_reads_more_than_limit_plus_one() -> None:
    response = StubResponse(chunks=[b"{}" + (b"x" * 100)])

    with pytest.raises(ProviderResponseLimitError):
        _fetch(response, max_bytes=2)

    assert response.closed


@pytest.mark.parametrize("body", [b"{", b"[]"])
def test_invalid_json_or_non_mapping_is_rejected_without_retry(body: bytes) -> None:
    response = StubResponse(body)
    calls = 0

    def get(*args: object, **kwargs: object) -> requests.Response:
        nonlocal calls
        calls += 1
        return response  # type: ignore[return-value]

    with pytest.raises(ProviderPayloadError):
        get_bounded_json(
            "https://provider.invalid/data",
            provider_key="test-provider",
            operation="test-operation",
            request_get=get,
        )

    assert calls == 1
    assert response.closed


def test_transient_status_retries_once_then_succeeds_after_closure() -> None:
    first = StubResponse(status_code=503)
    second = StubResponse(b'{"ok":true}')
    responses = [first, second]
    sleeps: list[float] = []

    def get(*args: object, **kwargs: object) -> requests.Response:
        return responses.pop(0)  # type: ignore[return-value]

    result = get_bounded_json(
        "https://provider.invalid/data",
        provider_key="test-provider",
        operation="test-operation",
        request_get=get,
        sleep=lambda delay: sleeps.append(delay),
    )

    assert result == {"ok": True}
    assert sleeps
    assert first.closed
    assert second.closed


def test_transient_connection_retry_exhaustion_is_bounded() -> None:
    calls = 0
    sleeps: list[float] = []

    def get(*args: object, **kwargs: object) -> requests.Response:
        nonlocal calls
        calls += 1
        raise requests.ConnectTimeout("sensitive upstream URL")

    with pytest.raises(ProviderTransportError, match="Provider request failed") as exc_info:
        get_bounded_json(
            "https://provider.invalid/data",
            provider_key="test-provider",
            operation="test-operation",
            request_get=get,
            sleep=lambda delay: sleeps.append(delay),
        )

    assert calls == 2
    assert len(sleeps) == 1
    assert "sensitive upstream URL" not in str(exc_info.value)


def test_non_retryable_4xx_is_attempted_once_and_closed() -> None:
    response = StubResponse(status_code=400)
    calls = 0

    def get(*args: object, **kwargs: object) -> requests.Response:
        nonlocal calls
        calls += 1
        return response  # type: ignore[return-value]

    with pytest.raises(ProviderTransportError):
        get_bounded_json(
            "https://provider.invalid/data",
            provider_key="test-provider",
            operation="test-operation",
            request_get=get,
        )

    assert calls == 1
    assert response.closed


def test_oversized_response_is_not_retried() -> None:
    response = StubResponse(headers={"Content-Length": "999"})
    calls = 0

    def get(*args: object, **kwargs: object) -> requests.Response:
        nonlocal calls
        calls += 1
        return response  # type: ignore[return-value]

    with pytest.raises(ProviderResponseLimitError):
        get_bounded_json(
            "https://provider.invalid/data",
            provider_key="test-provider",
            operation="test-operation",
            request_get=get,
            max_bytes=2,
        )

    assert calls == 1
    assert response.closed


def test_transport_errors_and_structured_logs_are_sanitized(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinel = "sentinel-query-secret"

    def get(*args: object, **kwargs: object) -> requests.Response:
        raise requests.ConnectionError(f"https://provider.invalid/data?key={sentinel}")

    caplog.set_level(logging.WARNING)
    with pytest.raises(ProviderTransportError) as exc_info:
        get_bounded_json(
            "https://provider.invalid/data",
            provider_key="test-provider",
            operation="test-operation",
            request_get=get,
            sleep=lambda delay: None,
        )

    assert sentinel not in str(exc_info.value)
    assert all(sentinel not in record.getMessage() for record in caplog.records)
    assert all(sentinel not in repr(record.__dict__) for record in caplog.records)
