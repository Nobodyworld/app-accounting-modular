from __future__ import annotations

import sys
from typing import Any

import pytest
import streamlit as st
from apps.web.api_session import (
    ApiLoginResult,
    clear_api_session,
    store_api_session,
)

from tests.streamlit_helpers import streamlit_app_path

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
    app = AppTest.from_file(streamlit_app_path())
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


def _lifecycle_test_app() -> None:
    import streamlit as st
    from apps.web.api_session import ApiLoginResult, store_api_session
    from apps.web.close_workspace import render_close_workspace

    if not st.session_state.get("test_session_initialized"):
        store_api_session(
            st.session_state,
            ApiLoginResult("access", "refresh", "bearer", "lifecycle-test"),
            email="accountant@example.test",
            organization_id=7,
        )
        st.session_state["test_session_initialized"] = True
    render_close_workspace(access_token="access", organization_id=7)


@pytest.mark.parametrize(
    ("initial_status", "action", "button_key", "final_status", "period_status"),
    [
        ("IN_PROGRESS", "ready", "close_mark_ready", "READY_FOR_APPROVAL", "OPEN"),
        ("READY_FOR_APPROVAL", "close", "close_final_action", "CLOSED", "CLOSED"),
        ("CLOSED", "reopen", "FormSubmitter:close_reopen_form-Reopen period", "IN_PROGRESS", "OPEN"),
    ],
)
def test_lifecycle_action_refreshes_visible_selectors_and_controls(
    monkeypatch: pytest.MonkeyPatch,
    initial_status: str,
    action: str,
    button_key: str,
    final_status: str,
    period_status: str,
) -> None:
    state = {"status": initial_status}
    writes: list[tuple[str, Any]] = []

    def fake_get(url: str, **_: Any) -> DummyResponse:
        status = state["status"]
        cycle = {"id": 2, "name": "March close", "status": status, "version": 2, "owner_user_id": 3}
        if url.endswith("/close/periods"):
            return DummyResponse(
                [{"id": 1, "label": "March 2027", "status": "CLOSED" if status == "CLOSED" else "OPEN"}]
            )
        if url.endswith("/close/periods/1/cycles"):
            return DummyResponse([cycle])
        if url.endswith("/close/cycles/2"):
            return DummyResponse(cycle)
        if url.endswith("/readiness"):
            return DummyResponse(
                {
                    "state": status,
                    "blocker_count": 0,
                    "completed_required_count": 8 if status == "CLOSED" else 6,
                    "required_task_count": 8,
                    "blockers": [],
                }
            )
        if url.endswith("/evidence/preview"):
            return DummyResponse({"freshness": "MISSING"})
        return DummyResponse([])

    def fake_post(url: str, **kwargs: Any) -> DummyResponse:
        writes.append((url, kwargs.get("json")))
        assert url.endswith(f"/close/cycles/2/{action}")
        state["status"] = final_status
        return DummyResponse({"id": 2, "status": final_status})

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setenv("API_BASE", "http://close.test")
    # AppTest replaces __main__; restore it before later Windows spawn tests.
    monkeypatch.setitem(sys.modules, "__main__", sys.modules["__main__"])
    app = AppTest.from_function(_lifecycle_test_app)
    app.run(timeout=20)
    assert not app.exception
    initial_selector_ids = [item.id for item in app.selectbox if item.label in {"Accounting period", "Close cycle"}]
    if action == "reopen":
        next(item for item in app.text_area if item.label == "Reopen reason").set_value("Synthetic review correction")
    app.button(key=button_key).click().run(timeout=20)
    assert not app.exception
    assert len(writes) == 1
    assert writes[0][1]["version"] == 2
    period_selector = next(item for item in app.selectbox if item.label == "Accounting period")
    cycle_selector = next(item for item in app.selectbox if item.label == "Close cycle")
    assert period_selector.options == [f"March 2027 · {period_status}"]
    assert cycle_selector.options == [f"March close · {final_status}"]
    # Recreate both widgets so the browser cannot retain obsolete option labels.
    assert period_selector.id not in initial_selector_ids
    assert cycle_selector.id not in initial_selector_ids
    assert any(f"Readiness: {final_status}" in str(item.value) for item in [*app.info, *app.success])
    assert next(item for item in app.button if item.label == "Generate variance reviews").disabled is (
        final_status != "IN_PROGRESS"
    )
    if final_status == "CLOSED":
        assert any(item.label == "Reopen period" for item in app.button)
    else:
        assert not any(item.label == "Reopen period" for item in app.button)
