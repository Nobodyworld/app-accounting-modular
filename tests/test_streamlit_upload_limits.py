"""Unit contracts for bounded budget and scenario-plan uploads."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from apps.api.limits import MAX_UPLOAD_BYTES
from apps.web.upload_limits import (
    BUDGET_UPLOAD_STATE_KEYS,
    SCENARIO_UPLOAD_STATE_KEYS,
    clear_budget_upload_state,
    clear_scenario_upload_state,
    read_bounded_upload,
    upload_limit_error,
    validate_stored_upload,
)


@dataclass
class FakeUpload:
    payload: bytes
    reported_size: int | None
    getvalue_calls: int = 0
    read_sizes: list[int] | None = None
    max_chunk: int | None = None
    read_offset: int = 0

    @property
    def size(self) -> int | None:
        return self.reported_size

    def getvalue(self) -> bytes:
        self.getvalue_calls += 1
        return self.payload

    def read(self, size: int = -1) -> bytes:
        if self.read_sizes is None:
            self.read_sizes = []
        self.read_sizes.append(size)
        requested = size if self.max_chunk is None else min(size, self.max_chunk)
        chunk = self.payload[self.read_offset : self.read_offset + requested]
        self.read_offset += len(chunk)
        return chunk


@pytest.mark.parametrize("kind", ["budget", "scenario-plan"])
def test_normal_upload_is_accepted_for_both_workflows(kind: str) -> None:
    upload = FakeUpload(payload=b"normal", reported_size=6)
    data, error = read_bounded_upload(upload)
    assert kind
    assert data == b"normal"
    assert error is None
    assert upload.getvalue_calls == 1


@pytest.mark.parametrize("kind", ["budget", "scenario-plan"])
def test_exact_maximum_upload_is_accepted_for_both_workflows(kind: str) -> None:
    upload = FakeUpload(payload=b"x" * MAX_UPLOAD_BYTES, reported_size=MAX_UPLOAD_BYTES)
    data, error = read_bounded_upload(upload)
    assert kind
    assert data is not None and len(data) == MAX_UPLOAD_BYTES
    assert error is None


@pytest.mark.parametrize("kind", ["budget", "scenario-plan"])
def test_reported_over_limit_upload_is_not_read_or_retained(kind: str) -> None:
    upload = FakeUpload(payload=b"x", reported_size=MAX_UPLOAD_BYTES + 1)
    data, error = read_bounded_upload(upload)
    assert kind
    assert data is None
    assert error == upload_limit_error()
    assert "1 MiB" in error
    assert upload.getvalue_calls == 0
    assert upload.read_sizes is None


@pytest.mark.parametrize("kind", ["budget", "scenario-plan"])
def test_unknown_size_upload_uses_only_a_bounded_read(kind: str) -> None:
    upload = FakeUpload(payload=b"x" * (MAX_UPLOAD_BYTES + 1), reported_size=None)
    data, error = read_bounded_upload(upload)
    assert kind
    assert data is None
    assert error == upload_limit_error()
    assert upload.getvalue_calls == 0
    assert upload.read_sizes == [MAX_UPLOAD_BYTES + 1]


def test_unknown_size_short_reads_are_accumulated_only_to_the_bound() -> None:
    upload = FakeUpload(payload=b"short-read", reported_size=None, max_chunk=2)
    data, error = read_bounded_upload(upload)
    assert data == b"short-read"
    assert error is None
    assert upload.read_sizes is not None
    assert all(size <= MAX_UPLOAD_BYTES + 1 for size in upload.read_sizes)


@pytest.mark.parametrize(
    ("clear", "keys"),
    [
        (clear_budget_upload_state, BUDGET_UPLOAD_STATE_KEYS),
        (clear_scenario_upload_state, SCENARIO_UPLOAD_STATE_KEYS),
    ],
)
def test_rejected_upload_clears_stale_bytes_preview_and_results(clear, keys: tuple[str, ...]) -> None:
    state = {key: b"stale" for key in keys}
    state["unrelated"] = "preserved"
    clear(state)
    assert all(key not in state for key in keys)
    assert state == {"unrelated": "preserved"}


@pytest.mark.parametrize("kind", ["budget", "scenario-plan"])
def test_over_limit_stored_bytes_are_rejected_before_reparsing(kind: str) -> None:
    data, error = validate_stored_upload(b"x" * (MAX_UPLOAD_BYTES + 1))
    assert kind
    assert data is None
    assert error == upload_limit_error()


def test_valid_stored_bytes_remain_available_to_normal_workflows() -> None:
    payload = b'{"metadata":{"name":"plan"},"scenarios":[{"name":"baseline"}]}'
    data, error = validate_stored_upload(payload)
    assert data == payload
    assert error is None
