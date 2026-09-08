from __future__ import annotations

import sys
from typing import Any

import pytest
import streamlit as st

pytest.importorskip("streamlit", reason="streamlit dependencies not available")
from streamlit.testing.v1 import AppTest  # type: ignore[import-not-found]


class DummyResponse:
    def __init__(self, payload: Any, status_code: int = 200, content: bytes = b"") -> None:
        self.payload = payload
        self.status_code = status_code
        self.text = ""
        self.content = content
        self.headers: dict[str, str] = {}

    def json(self) -> Any:
        return self.payload


def _feedback_test_app() -> None:
    from apps.web.api_session import ApiLoginResult, store_api_session
    from apps.web.close_workspace import render_close_workspace

    if not st.session_state.get("test_session_initialized"):
        store_api_session(
            st.session_state,
            ApiLoginResult("access", "refresh", "bearer", "feedback-test"),
            email="accountant@example.test",
            organization_id=7,
        )
        st.session_state["test_session_initialized"] = True
    render_close_workspace(access_token="access", organization_id=7)


def _base_get(state: dict[str, Any], url: str) -> DummyResponse:
    cycle = {
        "id": 2,
        "name": "March close",
        "status": "IN_PROGRESS",
        "owner_user_id": 3,
        "due_date": "2027-04-05",
        "version": 2,
    }
    if url.endswith("/close/periods"):
        return DummyResponse([{"id": 1, "label": "March 2027", "status": "OPEN"}])
    if url.endswith("/close/periods/1/cycles"):
        return DummyResponse([cycle])
    if url.endswith("/close/cycles/2"):
        return DummyResponse(cycle)
    if url.endswith("/close/cycles/2/readiness"):
        return DummyResponse(
            {
                "state": "IN_PROGRESS",
                "blocker_count": 0,
                "completed_required_count": 6,
                "required_task_count": 8,
                "blockers": [],
            }
        )
    if "/reconciliations?" in url:
        return DummyResponse([dict(item) for item in state.get("reconciliations", [])])
    if "/variance-reviews?" in url:
        return DummyResponse([])
    if "/journal-approvals/" in url and "/history?" in url:
        return DummyResponse([dict(item) for item in state.get("approval_history", [])])
    if "/journal-approvals?" in url:
        return DummyResponse([dict(item) for item in state.get("approvals", [])])
    if url.endswith("/checklist"):
        return DummyResponse([dict(item) for item in state.get("checklist", [])])
    if url.endswith("/evidence/preview"):
        return DummyResponse({"freshness": "MISSING", "source_version": 2})
    return DummyResponse([])


def _configure_app(monkeypatch: pytest.MonkeyPatch, state: dict[str, Any], *, post: Any, patch: Any) -> AppTest:
    monkeypatch.setattr("requests.get", lambda url, **_kwargs: _base_get(state, url))
    monkeypatch.setattr("requests.post", post)
    monkeypatch.setattr("requests.patch", patch)
    monkeypatch.setenv("API_BASE", "http://close.test")
    monkeypatch.setitem(sys.modules, "__main__", sys.modules["__main__"])
    app = AppTest.from_function(_feedback_test_app)
    app.run(timeout=20)
    assert not app.exception
    return app


def test_reconciliation_approval_rerenders_fresh_server_table(monkeypatch: pytest.MonkeyPatch) -> None:
    state: dict[str, Any] = {
        "reconciliations": [
            {
                "id": 11,
                "account_id": 1000,
                "ledger_ending_balance": "355.00",
                "control_balance": "355.00",
                "difference": "0.00",
                "tolerance": "0.00",
                "status": "PREPARED",
                "prepared_by_id": 3,
                "approved_by_id": None,
                "version": 1,
            }
        ]
    }
    writes: list[str] = []

    def fake_post(url: str, **_kwargs: Any) -> DummyResponse:
        writes.append(url)
        assert url.endswith("/close/cycles/2/reconciliations/11/approve")
        state["reconciliations"][0].update({"status": "APPROVED", "approved_by_id": 4, "version": 2})
        return DummyResponse(dict(state["reconciliations"][0]))

    app = _configure_app(
        monkeypatch,
        state,
        post=fake_post,
        patch=lambda *_args, **_kwargs: DummyResponse({}),
    )
    next(item for item in app.button if item.label == "Approve independently").click().run(timeout=20)

    assert not app.exception
    assert len(writes) == 1
    assert any("APPROVED" in str(item.value) and "1000" in str(item.value) for item in app.dataframe)
    assert any("Reconciliation independently approved." in str(item.value) for item in app.success)


def test_checklist_update_rerenders_fresh_server_table(monkeypatch: pytest.MonkeyPatch) -> None:
    state: dict[str, Any] = {
        "checklist": [
            {
                "id": 21,
                "title": "Provider/report freshness attestation",
                "category": "freshness",
                "control_type": "MANUAL",
                "task_key": "freshness_attestation",
                "required": True,
                "status": "PENDING",
                "owner_user_id": 3,
                "due_date": "2027-04-05",
                "version": 1,
            }
        ]
    }
    writes: list[str] = []

    def fake_patch(url: str, **_kwargs: Any) -> DummyResponse:
        writes.append(url)
        assert url.endswith("/close/cycles/2/checklist/21")
        state["checklist"][0].update({"status": "COMPLETE", "version": 2})
        return DummyResponse(dict(state["checklist"][0]))

    app = _configure_app(
        monkeypatch,
        state,
        post=lambda *_args, **_kwargs: DummyResponse({}),
        patch=fake_patch,
    )
    next(item for item in app.checkbox if item.label == "Mark complete").set_value(True)
    next(item for item in app.button if item.label == "Update task").click().run(timeout=20)

    assert not app.exception
    assert len(writes) == 1
    assert any("COMPLETE" in str(item.value) and "freshness" in str(item.value).lower() for item in app.dataframe)
    assert any("Checklist task updated." in str(item.value) for item in app.success)


def test_denied_journal_decision_is_visible_immediately_and_does_not_mutate(monkeypatch: pytest.MonkeyPatch) -> None:
    state: dict[str, Any] = {
        "approvals": [
            {
                "id": 31,
                "transaction_id": 41,
                "staged_transaction_id": None,
                "requestor_user_id": 3,
                "status": "REQUESTED",
                "decided_by_id": None,
                "version": 1,
            }
        ],
        "approval_history": [],
    }
    writes: list[str] = []

    def fake_post(url: str, **_kwargs: Any) -> DummyResponse:
        writes.append(url)
        assert url.endswith("/close/cycles/2/journal-approvals/31/decide")
        return DummyResponse(
            {
                "detail": {
                    "code": "CLOSE_CONFLICT",
                    "message": "A journal approval requestor cannot approve their own request",
                }
            },
            status_code=409,
        )

    app = _configure_app(
        monkeypatch,
        state,
        post=fake_post,
        patch=lambda *_args, **_kwargs: DummyResponse({}),
    )
    next(item for item in app.button if item.label == "Record independent decision").click().run(timeout=20)

    assert not app.exception
    assert len(writes) == 1
    assert state["approvals"][0]["status"] == "REQUESTED"
    assert any(
        "CLOSE_CONFLICT: A journal approval requestor cannot approve their own request" in str(item.value)
        for item in app.error
    )
