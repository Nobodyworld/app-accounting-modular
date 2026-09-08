from __future__ import annotations

import sys
from typing import Any

import pytest

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
    import streamlit as st
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


def _cycle(state: dict[str, Any]) -> dict[str, Any]:
    return dict(
        state.get(
            "cycle",
            {
                "id": 2,
                "name": "March close",
                "status": "IN_PROGRESS",
                "owner_user_id": 3,
                "due_date": "2027-04-05",
                "version": 2,
            },
        )
    )


def _readiness(state: dict[str, Any]) -> dict[str, Any]:
    return dict(
        state.get(
            "readiness",
            {
                "state": "IN_PROGRESS",
                "blocker_count": 0,
                "completed_required_count": 6,
                "required_task_count": 8,
                "blockers": [],
            },
        )
    )


def _base_get(state: dict[str, Any], url: str) -> DummyResponse:
    cycle = _cycle(state)
    if url.endswith("/close/periods"):
        return DummyResponse([{"id": 1, "label": "March 2027", "status": "OPEN"}])
    if url.endswith("/close/periods/1/cycles"):
        return DummyResponse([cycle])
    if url.endswith("/close/cycles/2"):
        return DummyResponse(cycle)
    if url.endswith("/close/cycles/2/readiness"):
        return DummyResponse(_readiness(state))
    if "/reconciliations?" in url:
        return DummyResponse([dict(item) for item in state.get("reconciliations", [])])
    if "/variance-reviews?" in url:
        return DummyResponse([dict(item) for item in state.get("variances", [])])
    if "/journal-approvals/" in url and "/history?" in url:
        return DummyResponse([dict(item) for item in state.get("approval_history", [])])
    if "/journal-approvals?" in url:
        return DummyResponse([dict(item) for item in state.get("approvals", [])])
    if url.endswith("/checklist"):
        return DummyResponse([dict(item) for item in state.get("checklist", [])])
    if url.endswith("/evidence/preview"):
        return DummyResponse(dict(state.get("evidence_preview", {"freshness": "MISSING", "source_version": 2})))
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


def _table(app: AppTest, *columns: str) -> Any:
    required = set(columns)
    return next(item.value for item in app.dataframe if required.issubset(set(item.value.columns)))


def test_mutate_surfaces_request_error_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.web import close_workspace

    messages: list[str] = []
    monkeypatch.setattr(close_workspace, "_org_params", lambda: {})
    monkeypatch.setattr(close_workspace, "_request", lambda *_args, **_kwargs: (None, "Session expired."))
    monkeypatch.setattr(close_workspace, "_render_mutation_error", messages.append)

    result = close_workspace._mutate("POST", "/close/example", None, success="unused")

    assert result is None
    assert messages == ["Session expired."]


def test_mutate_surfaces_missing_response_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    from apps.web import close_workspace

    messages: list[str] = []
    monkeypatch.setattr(close_workspace, "_org_params", lambda: {})
    monkeypatch.setattr(close_workspace, "_request", lambda *_args, **_kwargs: (None, None))
    monkeypatch.setattr(close_workspace, "_render_mutation_error", messages.append)

    result = close_workspace._mutate("POST", "/close/example", None, success="unused")

    assert result is None
    assert messages == ["The close request did not return a response."]


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
    table = _table(app, "Account", "Status")
    visible = table.loc[table["Account"] == 1000]
    assert visible["Status"].tolist() == ["APPROVED"]
    assert any("Reconciliation independently approved." in str(item.value) for item in app.success)


def test_staged_journal_processing_rerenders_blockers(monkeypatch: pytest.MonkeyPatch) -> None:
    state: dict[str, Any] = {
        "readiness": {
            "state": "BLOCKED",
            "blocker_count": 1,
            "completed_required_count": 5,
            "required_task_count": 8,
            "blockers": [
                {
                    "code": "STAGED_ITEMS_UNRESOLVED",
                    "category": "journals",
                    "message": "A staged journal remains unresolved.",
                    "recommended_action": "Process the staged journal.",
                    "source_entity_type": "staged_transaction",
                    "source_entity_id": "51",
                }
            ],
        }
    }
    writes: list[str] = []

    def fake_post(url: str, **_kwargs: Any) -> DummyResponse:
        writes.append(url)
        assert url.endswith("/workflow/process")
        state["readiness"] = {
            "state": "IN_PROGRESS",
            "blocker_count": 0,
            "completed_required_count": 6,
            "required_task_count": 8,
            "blockers": [],
        }
        return DummyResponse({"processed": [51]})

    app = _configure_app(
        monkeypatch,
        state,
        post=fake_post,
        patch=lambda *_args, **_kwargs: DummyResponse({}),
    )
    next(item for item in app.button if item.label == "Process next staged journal").click().run(timeout=20)

    assert not app.exception
    assert writes == ["http://close.test/workflow/process"]
    assert any("No server-derived blockers remain." in str(item.value) for item in app.success)
    assert any("Staged journal 51 processed" in str(item.value) for item in app.success)


def test_variance_disposition_rerenders_fresh_server_table(monkeypatch: pytest.MonkeyPatch) -> None:
    state: dict[str, Any] = {
        "variances": [
            {
                "id": 61,
                "account_id": 4000,
                "period_start": "2027-03-01",
                "budget_amount": "-300.00",
                "actual_amount": "-500.00",
                "variance_amount": "-200.00",
                "is_material": True,
                "disposition": "OPEN",
                "version": 1,
            }
        ]
    }
    writes: list[str] = []

    def fake_patch(url: str, **_kwargs: Any) -> DummyResponse:
        writes.append(url)
        assert url.endswith("/close/cycles/2/variance-reviews/61")
        state["variances"][0].update({"disposition": "EXPLAINED", "version": 2})
        return DummyResponse(dict(state["variances"][0]))

    app = _configure_app(
        monkeypatch,
        state,
        post=lambda *_args, **_kwargs: DummyResponse({}),
        patch=fake_patch,
    )
    next(item for item in app.button if item.label == "Record disposition").click().run(timeout=20)

    assert not app.exception
    assert len(writes) == 1
    table = _table(app, "Account", "Disposition")
    visible = table.loc[table["Account"] == 4000]
    assert visible["Disposition"].tolist() == ["EXPLAINED"]
    assert any("Variance disposition recorded." in str(item.value) for item in app.success)


def test_journal_decision_rerenders_row_and_history(monkeypatch: pytest.MonkeyPatch) -> None:
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
        state["approvals"][0].update({"status": "APPROVED", "decided_by_id": 4, "version": 2})
        state["approval_history"] = [
            {
                "from_status": "REQUESTED",
                "to_status": "APPROVED",
                "decided_by_id": 4,
                "decided_at": "2027-04-01T12:00:00Z",
                "reason": "Independent review complete.",
            }
        ]
        return DummyResponse(dict(state["approvals"][0]))

    app = _configure_app(
        monkeypatch,
        state,
        post=fake_post,
        patch=lambda *_args, **_kwargs: DummyResponse({}),
    )
    next(item for item in app.button if item.label == "Record independent decision").click().run(timeout=20)

    assert not app.exception
    assert len(writes) == 1
    approvals = _table(app, "Requestor", "Status", "Decided by")
    assert approvals["Status"].tolist() == ["APPROVED"]
    history = _table(app, "From", "To", "Decided by")
    assert history["To"].tolist() == ["APPROVED"]
    assert any("Journal approval decision recorded." in str(item.value) for item in app.success)


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


def test_custom_checklist_creation_rerenders_fresh_server_table(monkeypatch: pytest.MonkeyPatch) -> None:
    state: dict[str, Any] = {"checklist": []}
    writes: list[str] = []

    def fake_post(url: str, **kwargs: Any) -> DummyResponse:
        writes.append(url)
        assert url.endswith("/close/cycles/2/checklist")
        body = kwargs["json"]
        row = {
            "id": 71,
            "title": body["title"],
            "category": "custom",
            "control_type": "MANUAL",
            "task_key": "custom_71",
            "required": body["required"],
            "status": "PENDING",
            "owner_user_id": body["owner_user_id"],
            "due_date": body["due_date"],
            "version": 1,
        }
        state["checklist"] = [row]
        return DummyResponse(dict(row))

    app = _configure_app(
        monkeypatch,
        state,
        post=fake_post,
        patch=lambda *_args, **_kwargs: DummyResponse({}),
    )
    next(item for item in app.text_input if item.label == "Custom task title").set_value("Tie out payroll support")
    next(item for item in app.button if item.label == "Add custom task").click().run(timeout=20)

    assert not app.exception
    assert len(writes) == 1
    table = _table(app, "Task", "Category", "Status")
    assert table["Task"].tolist() == ["Tie out payroll support"]
    assert any("Custom checklist task added." in str(item.value) for item in app.success)


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
    table = _table(app, "Task", "Status")
    visible = table.loc[table["Task"] == "Provider/report freshness attestation"]
    assert visible["Status"].tolist() == ["COMPLETE"]
    assert any("Checklist task updated." in str(item.value) for item in app.success)


def test_evidence_generation_rerenders_freshness_and_keeps_result(monkeypatch: pytest.MonkeyPatch) -> None:
    state: dict[str, Any] = {"evidence_preview": {"freshness": "MISSING", "source_version": 2}}
    writes: list[str] = []

    def fake_post(url: str, **_kwargs: Any) -> DummyResponse:
        writes.append(url)
        assert url.endswith("/close/cycles/2/evidence")
        state["evidence_preview"] = {
            "freshness": "CURRENT",
            "source_version": 2,
            "latest_manifest_sha256": "abc123",
        }
        return DummyResponse({"manifest_sha256": "abc123"})

    app = _configure_app(
        monkeypatch,
        state,
        post=fake_post,
        patch=lambda *_args, **_kwargs: DummyResponse({}),
    )
    next(item for item in app.button if item.label == "Generate draft evidence").click().run(timeout=20)

    assert not app.exception
    assert len(writes) == 1
    assert any("Deterministic draft close evidence generated" in str(item.value) for item in app.success)
    assert any("abc123" in str(item.value) for item in app.code)
