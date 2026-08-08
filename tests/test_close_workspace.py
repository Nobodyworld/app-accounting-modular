from __future__ import annotations

from typing import Any

import pytest
import streamlit as st
from apps.web.api_session import (
    ApiLoginResult,
    clear_api_session,
    store_api_session,
)

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

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("request failed")


def test_close_session_state_is_cleared_on_logout_and_replacement() -> None:
    state: dict[str, Any] = {}
    result = ApiLoginResult("access", "refresh", "bearer", "session-one")
    store_api_session(state, result, email="accountant@example.test", organization_id=7)
    state.update(
        {
            "close_selected_cycle_id": 11,
            "close_readiness": {"tenant": 7},
            "close_evidence_result": {"secret": "must-clear"},
            "close_dynamic_widget_not_in_static_registry": "must-clear",
        }
    )
    clear_api_session(state)
    assert not any(key.startswith("close_") for key in state)


def test_close_workspace_renders_blocked_authenticated_structure(monkeypatch: pytest.MonkeyPatch) -> None:
    access_value = "close-test-access"

    def fake_get(url: str, **_: Any) -> DummyResponse:
        if url.endswith("/health"):
            return DummyResponse({"status": "ok"})
        if url.endswith("/health/ready"):
            return DummyResponse({"status": "ok", "reports": []})
        if url.endswith("/providers"):
            return DummyResponse({"providers": []})
        if url.endswith("/close/periods"):
            return DummyResponse(
                [
                    {
                        "id": 1,
                        "label": "March 2027",
                        "status": "OPEN",
                        "start_date": "2027-03-01",
                        "end_date": "2027-03-31",
                    }
                ]
            )
        if url.endswith("/close/periods/1/cycles"):
            return DummyResponse([{"id": 2, "name": "March close", "status": "IN_PROGRESS"}])
        if url.endswith("/close/cycles/2"):
            return DummyResponse(
                {
                    "id": 2,
                    "name": "March close",
                    "status": "IN_PROGRESS",
                    "owner_user_id": 3,
                    "due_date": "2027-04-05",
                    "version": 2,
                }
            )
        if url.endswith("/close/cycles/2/readiness"):
            blocker = {
                "code": "RECONCILIATIONS_MISSING",
                "category": "reconciliations",
                "message": "No account reconciliations have been prepared.",
                "source_entity_type": "close_cycle",
                "source_entity_id": "2",
                "recommended_action": "Prepare and independently approve required account reconciliations.",
            }
            return DummyResponse(
                {
                    "state": "BLOCKED",
                    "blocker_count": 1,
                    "warning_count": 1,
                    "completed_required_count": 4,
                    "required_task_count": 8,
                    "blockers": [blocker],
                    "cycle_status": "IN_PROGRESS",
                }
            )
        if url.endswith("/reconciliations") or url.endswith("/variance-reviews") or url.endswith("/journal-approvals"):
            return DummyResponse([])
        if url.endswith("/checklist"):
            return DummyResponse([])
        if url.endswith("/evidence/preview"):
            return DummyResponse({"freshness": "MISSING", "source_version": 2})
        if url.endswith("/evidence/download"):
            return DummyResponse({}, status_code=404)
        return DummyResponse({"ok": True})

    def fake_post(url: str, **_: Any) -> DummyResponse:
        if url.endswith("/auth/token"):
            return DummyResponse(
                {
                    "access_token": access_value,
                    "refresh_token": "close-test-refresh",
                    "token_type": "bearer",
                    "session_id": "close-test-session",
                }
            )
        return DummyResponse({"ok": True})

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setattr("requests.patch", lambda *_args, **_kwargs: DummyResponse({"ok": True}))
    monkeypatch.setenv("API_BASE", "http://close.test")
    monkeypatch.setenv("STREAMLIT_TESTING", "1")
    st.cache_data.clear()
    app = AppTest.from_file("apps/web/app.py")
    app.run(timeout=20)
    app.text_input(key="api_login_email").set_value("accountant@example.test")
    app.text_input(key="api_login_password").set_value("password")
    app.number_input(key="api_organization_input").set_value(7)
    app.button(key="api_login_button").click()
    app.run(timeout=20)
    visible = " ".join(
        str(element.value)
        for element in [*app.markdown, *app.caption, *app.info, *app.warning, *app.success, *app.error]
    )
    assert any(element.value == "Close Workspace" for element in app.subheader)
    assert "Readiness: BLOCKED" in visible
    assert app.dataframe
    assert not app.exception
