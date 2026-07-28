"""Reusable size enforcement for Streamlit uploads and retained bytes."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any, Protocol

from apps.api.limits import MAX_UPLOAD_BYTES

BUDGET_UPLOAD_STATE_KEYS = ("uploaded_budget_bytes", "uploaded_budget_preview")
SCENARIO_UPLOAD_STATE_KEYS = ("scenario_plan_bytes", "scenario_plan_name", "scenario_plan_preview")


class UploadedFileLike(Protocol):
    """Streamlit upload operations used by the bounded reader."""

    @property
    def size(self) -> int | None:
        """Return the reported upload size when available."""

    def getvalue(self) -> bytes:
        """Return uploaded bytes."""

    def read(self, size: int = -1) -> bytes:
        """Read at most ``size`` bytes."""


def upload_limit_label(max_bytes: int = MAX_UPLOAD_BYTES) -> str:
    """Return a reader-friendly binary size label."""

    return f"{max_bytes / (1024 * 1024):g} MiB"


def upload_limit_error(max_bytes: int = MAX_UPLOAD_BYTES) -> str:
    """Return the stable visible rejection message."""

    return f"Upload exceeds the {upload_limit_label(max_bytes)} application limit."


def read_bounded_upload(
    uploaded_file: UploadedFileLike,
    *,
    max_bytes: int = MAX_UPLOAD_BYTES,
) -> tuple[bytes | None, str | None]:
    """Read an upload without ever accumulating more than ``max_bytes + 1`` bytes."""

    if max_bytes <= 0:
        raise ValueError("max_bytes must be greater than zero")

    reported_size = getattr(uploaded_file, "size", None)
    if isinstance(reported_size, int) and not isinstance(reported_size, bool):
        if reported_size < 0 or reported_size > max_bytes:
            return None, upload_limit_error(max_bytes)
        data = uploaded_file.getvalue()
    else:
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = uploaded_file.read(remaining)
            if not isinstance(chunk, bytes | bytearray | memoryview):
                return None, "Uploaded file did not provide binary data."
            if not chunk:
                break
            payload_chunk = bytes(chunk)
            if len(payload_chunk) > remaining:
                return None, upload_limit_error(max_bytes)
            chunks.append(payload_chunk)
            remaining -= len(payload_chunk)
        data = b"".join(chunks)

    if not isinstance(data, bytes | bytearray | memoryview):
        return None, "Uploaded file did not provide binary data."
    payload = bytes(data)
    if len(payload) > max_bytes:
        return None, upload_limit_error(max_bytes)
    return payload, None


def validate_stored_upload(
    value: object,
    *,
    max_bytes: int = MAX_UPLOAD_BYTES,
) -> tuple[bytes | None, str | None]:
    """Validate bytes before session-state content is parsed again."""

    if not isinstance(value, bytes | bytearray | memoryview):
        return None, "Stored upload data is invalid; upload the file again."
    payload = bytes(value)
    if len(payload) > max_bytes:
        return None, upload_limit_error(max_bytes)
    return payload, None


def clear_upload_state(state: MutableMapping[str, Any], keys: tuple[str, ...]) -> None:
    """Clear all retained input and result state associated with an upload."""

    for key in keys:
        state.pop(key, None)


def clear_budget_upload_state(state: MutableMapping[str, Any]) -> None:
    clear_upload_state(state, BUDGET_UPLOAD_STATE_KEYS)


def clear_scenario_upload_state(state: MutableMapping[str, Any]) -> None:
    clear_upload_state(state, SCENARIO_UPLOAD_STATE_KEYS)
