"""Tests for the Streamlit authenticated utility-session helpers."""

from __future__ import annotations

from typing import Any

from apps.web.api_session import (
    ACCESS_TOKEN_KEY,
    AUTH_EMAIL_KEY,
    ORGANIZATION_ID_KEY,
    PROTECTED_UTILITY_STATE_KEYS,
    SESSION_ID_KEY,
    ApiLoginResult,
    api_error_detail,
    auth_headers,
    authenticated_workspace_ready,
    clear_api_session,
    clear_protected_utility_state,
    request_access_token,
    store_api_session,
)


class DummyResponse:
    """Small response double matching the helper protocol."""

    def __init__(self, status_code: int, payload: Any = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def test_auth_headers_require_non_empty_token() -> None:
    assert auth_headers(None) == {}
    assert auth_headers("  ") == {}
    assert auth_headers(" token-value ") == {"Authorization": "Bearer token-value"}


def test_authenticated_workspace_requires_token_and_positive_organization() -> None:
    assert authenticated_workspace_ready("token", 1) is True
    assert authenticated_workspace_ready("token", 0) is False
    assert authenticated_workspace_ready("token", None) is False
    assert authenticated_workspace_ready("", 1) is False


def test_request_access_token_normalizes_credentials_and_validates_payload() -> None:
    captured: dict[str, Any] = {}
    token_value = "-".join(("signed", "token"))

    def fake_post(url: str, **kwargs: Any) -> DummyResponse:
        captured["url"] = url
        captured.update(kwargs)
        return DummyResponse(
            200,
            {
                "access_token": token_value,
                "token_type": "bearer",
                "session_id": "session-123",
            },
        )

    result, error = request_access_token(
        "http://api.example/",
        " User@Example.COM ",
        "secret",
        post=fake_post,
    )

    assert error is None
    assert result == ApiLoginResult(
        access_token=token_value,
        token_type="bearer",
        session_id="session-123",
    )
    assert captured["url"] == "http://api.example/auth/token"
    assert captured["data"] == {"username": "user@example.com", "password": "secret"}
    assert captured["timeout"] == 10


def test_request_access_token_returns_api_detail_for_failed_login() -> None:
    result, error = request_access_token(
        "http://api.example",
        "user@example.com",
        "wrong",
        post=lambda *_args, **_kwargs: DummyResponse(400, {"detail": "Incorrect username or password"}),
    )

    assert result is None
    assert error == "Incorrect username or password"


def test_request_access_token_rejects_malformed_success_payload() -> None:
    result, error = request_access_token(
        "http://api.example",
        "user@example.com",
        "secret",
        post=lambda *_args, **_kwargs: DummyResponse(200, {"token_type": "bearer"}),
    )

    assert result is None
    assert error == "Authentication response did not include an access token."


def test_api_error_detail_flattens_validation_messages() -> None:
    response = DummyResponse(
        422,
        {
            "detail": [
                {"loc": ["query", "organization_id"], "msg": "Field required"},
                {"loc": ["query", "base"], "msg": "String should have at most 3 characters"},
            ]
        },
    )

    assert api_error_detail(response) == "Field required; String should have at most 3 characters"


def test_api_error_detail_falls_back_to_text_and_status() -> None:
    assert api_error_detail(DummyResponse(500, ValueError("invalid json"), "upstream unavailable")) == (
        "upstream unavailable"
    )
    assert api_error_detail(DummyResponse(503, ValueError("invalid json"))) == "Request failed with status 503"


def test_clear_protected_utility_state_preserves_public_workflows() -> None:
    state: dict[str, Any] = {
        **{key: {"tenant": 7} for key in PROTECTED_UTILITY_STATE_KEYS},
        "snapshot_controls_payload": {"public": True},
        "scenario_plan_preview": {"scenario_count": 1},
        "uploaded_budget_preview": "local-preview",
    }

    clear_protected_utility_state(state)

    assert all(key not in state for key in PROTECTED_UTILITY_STATE_KEYS)
    assert state == {
        "snapshot_controls_payload": {"public": True},
        "scenario_plan_preview": {"scenario_count": 1},
        "uploaded_budget_preview": "local-preview",
    }


def test_store_api_session_purges_prior_tenant_state_before_organization_change() -> None:
    state: dict[str, Any] = {
        ACCESS_TOKEN_KEY: "old-token",
        SESSION_ID_KEY: "old-session",
        AUTH_EMAIL_KEY: "old@example.com",
        ORGANIZATION_ID_KEY: 7,
        "cashflow_report_payload": {"organization_id": 7},
        "budget_report_error": "organization 7 error",
        "snapshot_base_input": "EUR",
    }
    token_value = "-".join(("new", "session", "token"))
    result = ApiLoginResult(access_token=token_value, token_type="bearer", session_id="new-session")

    store_api_session(state, result, email=" New@Example.com ", organization_id=12)

    assert state[ACCESS_TOKEN_KEY] == token_value
    assert state[SESSION_ID_KEY] == "new-session"
    assert state[AUTH_EMAIL_KEY] == "new@example.com"
    assert state[ORGANIZATION_ID_KEY] == 12
    assert "cashflow_report_payload" not in state
    assert "budget_report_error" not in state
    assert state["snapshot_base_input"] == "EUR"


def test_store_and_clear_api_session_do_not_store_passwords_or_tenant_results() -> None:
    state: dict[str, Any] = {
        "unrelated": "keep",
        "cashflow_report_payload": {"organization_id": 7},
        "market_sync_error": "stale tenant error",
        "snapshot_base_input": "EUR",
    }
    token_value = "-".join(("session", "token"))
    result = ApiLoginResult(access_token=token_value, token_type="bearer", session_id="session")

    store_api_session(state, result, email=" User@Example.com ", organization_id=7)

    assert state[ACCESS_TOKEN_KEY] == token_value
    assert state[SESSION_ID_KEY] == "session"
    assert state[AUTH_EMAIL_KEY] == "user@example.com"
    assert state[ORGANIZATION_ID_KEY] == 7
    assert "password" not in state
    assert "cashflow_report_payload" not in state
    assert "market_sync_error" not in state

    state["budget_report_payload"] = {"organization_id": 7}
    state["fx_sync_error"] = "stale tenant error"
    clear_api_session(state)

    assert state == {
        "unrelated": "keep",
        "snapshot_base_input": "EUR",
    }
