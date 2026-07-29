"""Authenticated API-session helpers for the Streamlit protected workspace."""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any, Protocol

import requests

ACCESS_TOKEN_KEY = "api_access_token"
REFRESH_TOKEN_KEY = "_api_refresh_token"
SESSION_ID_KEY = "api_session_id"
AUTH_EMAIL_KEY = "api_authenticated_email"
ORGANIZATION_ID_KEY = "api_organization_id"
PROTECTED_UTILITY_STATE_KEYS = (
    "budget_report_payload",
    "budget_report_error",
    "cashflow_report_payload",
    "cashflow_report_error",
    "fx_sync_payload",
    "fx_sync_error",
    "market_sync_payload",
    "market_sync_error",
    "scenario_plan_preview",
)


class HttpResponse(Protocol):
    """Minimal HTTP response contract used by the session helpers."""

    status_code: int
    text: str

    def json(self) -> Any:
        """Return the decoded JSON body."""


PostRequest = Callable[..., HttpResponse]


@dataclass(frozen=True, slots=True)
class ApiLoginResult:
    """Validated authentication response safe to place in Streamlit session state."""

    access_token: str
    refresh_token: str
    token_type: str
    session_id: str


def auth_headers(access_token: str | None) -> dict[str, str]:
    """Return a bearer header only when a non-empty access token is available."""

    token = (access_token or "").strip()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def authenticated_workspace_ready(access_token: str | None, organization_id: int | None) -> bool:
    """Return whether protected workspace actions have authentication and organization scope."""

    if not (access_token or "").strip():
        return False
    try:
        return int(organization_id or 0) > 0
    except (TypeError, ValueError):
        return False


def api_error_detail(response: HttpResponse) -> str:
    """Extract a useful API error without exposing credentials or raw response objects."""

    try:
        payload = response.json()
    except Exception:
        payload = None

    if isinstance(payload, Mapping):
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
        if isinstance(detail, list):
            messages = [
                str(item.get("msg", "")).strip()
                for item in detail
                if isinstance(item, Mapping) and str(item.get("msg", "")).strip()
            ]
            if messages:
                return "; ".join(messages)
        for key in ("message", "error"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    text = getattr(response, "text", "")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return f"Request failed with status {response.status_code}"


def request_access_token(
    api_base: str,
    email: str,
    password: str,
    *,
    timeout: int = 10,
    post: PostRequest = requests.post,
) -> tuple[ApiLoginResult | None, str | None]:
    """Exchange credentials for a validated access-token payload."""

    normalized_email = email.strip().lower()
    if not normalized_email:
        return None, "Email is required."
    if not password:
        return None, "Password is required."

    try:
        response = post(
            f"{api_base.rstrip('/')}/auth/token",
            data={"username": normalized_email, "password": password},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        return None, f"Authentication service unavailable: {exc}"
    except Exception as exc:  # pragma: no cover - defensive adapter boundary
        return None, f"Authentication request failed: {exc}"

    if response.status_code >= 400:
        return None, api_error_detail(response)

    try:
        payload = response.json()
    except Exception:
        return None, "Authentication response was not valid JSON."
    if not isinstance(payload, Mapping):
        return None, "Authentication response was malformed."

    return _parse_token_pair(payload, response_name="Authentication")


def _parse_token_pair(
    payload: Mapping[str, Any],
    *,
    response_name: str,
) -> tuple[ApiLoginResult | None, str | None]:
    """Validate a bounded token-pair payload without echoing credential values."""

    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    token_type = payload.get("token_type")
    session_id = payload.get("session_id")
    if not isinstance(access_token, str) or not access_token.strip() or len(access_token) > 4096:
        return None, f"{response_name} response did not include a valid access token."
    if not isinstance(refresh_token, str) or not refresh_token.strip() or len(refresh_token) > 4096:
        return None, f"{response_name} response did not include a valid refresh token."
    if not isinstance(token_type, str) or token_type.lower() != "bearer":
        return None, f"{response_name} response did not include a bearer token type."
    if not isinstance(session_id, str) or not session_id.strip() or len(session_id) > 64:
        return None, f"{response_name} response included an invalid session identifier."
    return (
        ApiLoginResult(
            access_token=access_token.strip(),
            refresh_token=refresh_token.strip(),
            token_type="bearer",
            session_id=session_id.strip(),
        ),
        None,
    )


def request_rotated_token_pair(
    api_base: str,
    refresh_token: str | None,
    *,
    timeout: int = 10,
    post: PostRequest = requests.post,
) -> tuple[ApiLoginResult | None, str | None]:
    """Request a one-time refresh rotation without surfacing credential-bearing errors."""

    token = (refresh_token or "").strip()
    if not token or len(token) > 4096:
        return None, "Session refresh is unavailable. Sign in again."
    try:
        response = post(
            f"{api_base.rstrip('/')}/auth/refresh",
            json={"refresh_token": token},
            timeout=timeout,
        )
    except Exception:
        return None, "Session refresh service is unavailable. Sign in again."
    if response.status_code >= 400:
        return None, "Session refresh was rejected. Sign in again."
    try:
        payload = response.json()
    except Exception:
        return None, "Session refresh response was invalid. Sign in again."
    if not isinstance(payload, Mapping):
        return None, "Session refresh response was malformed. Sign in again."
    return _parse_token_pair(payload, response_name="Session refresh")


def request_server_logout(
    api_base: str,
    access_token: str | None,
    *,
    timeout: int = 10,
    post: PostRequest = requests.post,
) -> tuple[bool, str | None]:
    """Attempt server-side revocation with a sanitized failure result."""

    headers = auth_headers(access_token)
    if not headers:
        return False, "Server logout was unavailable; local session data was cleared."
    try:
        response = post(
            f"{api_base.rstrip('/')}/auth/logout",
            headers=headers,
            timeout=timeout,
        )
    except Exception:
        return False, "Server logout was unavailable; local session data was cleared."
    if response.status_code >= 400:
        return False, "Server logout could not be confirmed; local session data was cleared."
    return True, None


def clear_protected_utility_state(state: MutableMapping[str, Any]) -> None:
    """Remove protected workspace results while preserving public and local-input state."""

    for key in PROTECTED_UTILITY_STATE_KEYS:
        state.pop(key, None)


def store_api_session(
    state: MutableMapping[str, Any],
    result: ApiLoginResult,
    *,
    email: str,
    organization_id: int,
) -> None:
    """Persist validated session values without storing the submitted password."""

    _validate_result(result)
    clear_protected_utility_state(state)
    state[ACCESS_TOKEN_KEY] = result.access_token
    state[REFRESH_TOKEN_KEY] = result.refresh_token
    state[SESSION_ID_KEY] = result.session_id
    state[AUTH_EMAIL_KEY] = email.strip().lower()
    state[ORGANIZATION_ID_KEY] = int(organization_id)


def clear_api_session(state: MutableMapping[str, Any]) -> None:
    """Remove authentication, organization scope, and protected workspace state."""

    clear_protected_utility_state(state)
    for key in (ACCESS_TOKEN_KEY, REFRESH_TOKEN_KEY, SESSION_ID_KEY, AUTH_EMAIL_KEY, ORGANIZATION_ID_KEY):
        state.pop(key, None)


def _validate_result(result: ApiLoginResult) -> None:
    """Reject incomplete manually constructed results before mutating state."""

    if (
        not result.access_token.strip()
        or len(result.access_token) > 4096
        or not result.refresh_token.strip()
        or len(result.refresh_token) > 4096
        or result.token_type.lower() != "bearer"
        or not result.session_id.strip()
        or len(result.session_id) > 64
    ):
        raise ValueError("Invalid API session result")


def replace_rotated_api_session(
    state: MutableMapping[str, Any],
    result: ApiLoginResult,
) -> None:
    """Atomically replace both credentials for the same server-side session."""

    _validate_result(result)
    current_session_id = state.get(SESSION_ID_KEY)
    if not isinstance(current_session_id, str) or current_session_id != result.session_id:
        raise ValueError("Rotated session identifier did not match")
    clear_protected_utility_state(state)
    state.update(
        {
            ACCESS_TOKEN_KEY: result.access_token,
            REFRESH_TOKEN_KEY: result.refresh_token,
            SESSION_ID_KEY: result.session_id,
        }
    )


ProtectedRequest = Callable[[dict[str, str]], HttpResponse]


def request_with_one_refresh(
    state: MutableMapping[str, Any],
    api_base: str,
    request: ProtectedRequest,
    *,
    post: PostRequest = requests.post,
) -> tuple[HttpResponse | None, str | None]:
    """Run a protected request with at most one refresh and one retry."""

    response = request(auth_headers(state.get(ACCESS_TOKEN_KEY)))
    if response.status_code != 401:
        return response, None

    result, _ = request_rotated_token_pair(
        api_base,
        state.get(REFRESH_TOKEN_KEY),
        post=post,
    )
    if result is None:
        clear_api_session(state)
        return None, "Your API session expired. Sign in again."
    try:
        replace_rotated_api_session(state, result)
    except ValueError:
        clear_api_session(state)
        return None, "Your API session could not be restored. Sign in again."

    retry_response = request(auth_headers(state.get(ACCESS_TOKEN_KEY)))
    if retry_response.status_code == 401:
        clear_api_session(state)
        return None, "Your API session could not be restored. Sign in again."
    return retry_response, None
