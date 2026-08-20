"""Streamlit access/refresh storage, rotation, retry, and logout lifecycle tests."""

from __future__ import annotations

from typing import Any

import requests
from apps.web.api_session import (
    ACCESS_TOKEN_KEY,
    AUTH_EMAIL_KEY,
    ORGANIZATION_ID_KEY,
    REFRESH_TOKEN_KEY,
    SESSION_ID_KEY,
    ApiLoginResult,
    clear_api_session,
    replace_rotated_api_session,
    request_access_token,
    request_rotated_token_pair,
    request_server_logout,
    request_with_one_refresh,
    store_api_session,
)


class DummyResponse:
    def __init__(self, status_code: int, payload: Any = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _result(access: str = "access-one", refresh: str = "refresh-one") -> ApiLoginResult:
    return ApiLoginResult(
        access_token=access,
        refresh_token=refresh,
        session_id="session-one",
        token_type="bearer",
    )


def _state() -> dict[str, Any]:
    state: dict[str, Any] = {"api_login_password": "must-not-persist"}
    store_api_session(state, _result(), email="user@example.com", organization_id=7)
    state.pop("api_login_password", None)
    return state


def test_login_requires_refresh_and_session_id_and_never_stores_password() -> None:
    payload = {
        "access_token": "access-one",
        "refresh_token": "refresh-one",
        "session_id": "session-one",
        "token_type": "bearer",
    }
    result, error = request_access_token(
        "https://api.example",
        "user@example.com",
        "password",
        post=lambda *_args, **_kwargs: DummyResponse(200, payload),
    )
    assert error is None
    assert result == _result()
    state: dict[str, Any] = {}
    assert result is not None
    store_api_session(state, result, email="user@example.com", organization_id=7)
    assert state[ACCESS_TOKEN_KEY] == "access-one"
    assert state[REFRESH_TOKEN_KEY] == "refresh-one"
    assert state[SESSION_ID_KEY] == "session-one"
    assert not any("password" in key.lower() for key in state)

    for missing in ("refresh_token", "session_id"):
        malformed = dict(payload)
        malformed.pop(missing)
        rejected, rejected_error = request_access_token(
            "https://api.example",
            "user@example.com",
            "password",
            post=lambda *_args, body=malformed, **_kwargs: DummyResponse(200, body),
        )
        assert rejected is None
        assert rejected_error is not None


def test_refresh_atomically_replaces_both_tokens_and_clears_protected_results() -> None:
    state = _state()
    state["budget_report_payload"] = {"sensitive": "old session"}
    state["provider_governance_catalog"] = {"organization_id": 7}
    replace_rotated_api_session(state, _result("access-two", "refresh-two"))
    assert state[ACCESS_TOKEN_KEY] == "access-two"
    assert state[REFRESH_TOKEN_KEY] == "refresh-two"
    assert "budget_report_payload" not in state
    assert "provider_governance_catalog" not in state


def test_session_replacement_and_organization_change_clear_provider_governance_state() -> None:
    state = _state()
    state["provider_governance_catalog"] = {"organization_id": 7}
    state["provider_governance_confirmation"] = "old organization"
    store_api_session(state, _result("access-two", "refresh-two"), email="user@example.com", organization_id=8)
    assert state[ORGANIZATION_ID_KEY] == 8
    assert "provider_governance_catalog" not in state
    assert "provider_governance_confirmation" not in state


def test_mismatched_rotated_session_leaves_credentials_unchanged() -> None:
    state = _state()
    next_access = "-".join(("access", "two"))
    next_refresh = "-".join(("refresh", "two"))
    mismatch = ApiLoginResult(
        access_token=next_access,
        refresh_token=next_refresh,
        session_id="different-session",
        token_type="bearer",
    )
    try:
        replace_rotated_api_session(state, mismatch)
    except ValueError:
        pass
    else:  # pragma: no cover - explicit atomicity assertion
        raise AssertionError("mismatched session must be rejected")
    assert state[ACCESS_TOKEN_KEY] == "access-one"
    assert state[REFRESH_TOKEN_KEY] == "refresh-one"


def test_protected_request_refreshes_and_retries_at_most_once() -> None:
    state = _state()
    request_headers: list[dict[str, str]] = []

    def protected(headers: dict[str, str]) -> DummyResponse:
        request_headers.append(headers)
        return DummyResponse(401 if len(request_headers) == 1 else 200, {"ok": True})

    response, error = request_with_one_refresh(
        state,
        "https://api.example",
        protected,
        post=lambda *_args, **_kwargs: DummyResponse(
            200,
            {
                "access_token": "access-two",
                "refresh_token": "refresh-two",
                "session_id": "session-one",
                "token_type": "bearer",
            },
        ),
    )
    assert error is None
    assert response is not None and response.status_code == 200
    assert len(request_headers) == 2
    assert request_headers == [
        {"Authorization": "Bearer access-one"},
        {"Authorization": "Bearer access-two"},
    ]
    assert state[REFRESH_TOKEN_KEY] == "refresh-two"


def test_failed_refresh_clears_authentication_and_protected_state() -> None:
    state = _state()
    state["cashflow_report_payload"] = {"tenant": 7}
    state["provider_governance_catalog"] = {"organization_id": 7}
    calls = 0

    def protected(_headers: dict[str, str]) -> DummyResponse:
        nonlocal calls
        calls += 1
        return DummyResponse(401, {"detail": "Could not validate credentials"})

    response, error = request_with_one_refresh(
        state,
        "https://api.example",
        protected,
        post=lambda *_args, **_kwargs: DummyResponse(401, {"detail": "rejected"}),
    )
    assert response is None
    assert error == "Your API session expired. Sign in again."
    assert calls == 1
    for key in (ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY, SESSION_ID_KEY, AUTH_EMAIL_KEY, ORGANIZATION_ID_KEY):
        assert key not in state
    assert "cashflow_report_payload" not in state
    assert "provider_governance_catalog" not in state


def test_logout_failure_is_sanitized_and_local_clear_removes_all_session_state() -> None:
    state = _state()
    state["market_sync_payload"] = {"tenant": 7}
    secret_refresh = str(state[REFRESH_TOKEN_KEY])

    def unavailable(*_args: object, **_kwargs: object) -> DummyResponse:
        raise requests.ConnectionError(f"failed near credential {secret_refresh}")

    confirmed, warning = request_server_logout(
        "https://api.example",
        state[ACCESS_TOKEN_KEY],
        post=unavailable,
    )
    assert confirmed is False
    assert warning == "Server logout was unavailable; local session data was cleared."
    assert secret_refresh not in warning
    clear_api_session(state)
    assert state == {}


def test_refresh_errors_never_echo_refresh_token() -> None:
    secret_refresh = "refresh-token-that-must-not-be-visible"

    def unavailable(*_args: object, **_kwargs: object) -> DummyResponse:
        raise requests.ConnectionError(secret_refresh)

    result, error = request_rotated_token_pair(
        "https://api.example",
        secret_refresh,
        post=unavailable,
    )
    assert result is None
    assert error is not None
    assert secret_refresh not in error
