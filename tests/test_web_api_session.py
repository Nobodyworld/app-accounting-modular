"""Tests for the Streamlit authenticated utility-session helpers."""

from __future__ import annotations

from typing import Any

from apps.web.api_session import (
    ACCESS_TOKEN_KEY,
    AUTH_EMAIL_KEY,
    ORGANIZATION_ID_KEY,
    SESSION_ID_KEY,
    ApiLoginResult,
    api_error_detail,
    auth_headers,
    authenticated_workspace_ready,
    clear_api_session,
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

    def fake_post(url: str, **kwargs: Any) -> DummyResponse:
        captured["url"] = url
        captured.update(kwargs)
        return DummyResponse(
            200,
            {
                "access_token": "signed-token",
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
        access_token="signed-token",
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


def test_store_and_clear_api_session_do_not_store_passwords() -> None:
    state: dict[str, Any] = {"unrelated": "keep"}
    result = ApiLoginResult(access_token="token", token_type="bearer", session_id="session")

    store_api_session(state, result, email=" User@Example.com ", organization_id=7)

    assert state[ACCESS_TOKEN_KEY] == "token"
    assert state[SESSION_ID_KEY] == "session"
    assert state[AUTH_EMAIL_KEY] == "user@example.com"
    assert state[ORGANIZATION_ID_KEY] == 7
    assert "password" not in state

    clear_api_session(state)

    assert state == {"unrelated": "keep"}
