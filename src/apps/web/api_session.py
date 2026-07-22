"""Authenticated API-session helpers for the Streamlit utility workspace."""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any, Protocol

import requests

ACCESS_TOKEN_KEY = "api_access_token"
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
    token_type: str
    session_id: str | None


def auth_headers(access_token: str | None) -> dict[str, str]:
    """Return a bearer header only when a non-empty access token is available."""

    token = (access_token or "").strip()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def authenticated_workspace_ready(access_token: str | None, organization_id: int | None) -> bool:
    """Return whether protected utility actions have authentication and tenant scope."""

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

    access_token = payload.get("access_token")
    token_type = payload.get("token_type")
    session_id = payload.get("session_id")
    if not isinstance(access_token, str) or not access_token.strip():
        return None, "Authentication response did not include an access token."
    if not isinstance(token_type, str) or token_type.lower() != "bearer":
        return None, "Authentication response did not include a bearer token type."
    if session_id is not None and not isinstance(session_id, str):
        return None, "Authentication response included an invalid session identifier."

    return (
        ApiLoginResult(
            access_token=access_token.strip(),
            token_type="bearer",
            session_id=session_id,
        ),
        None,
    )


def clear_protected_utility_state(state: MutableMapping[str, Any]) -> None:
    """Remove tenant-scoped utility payloads and errors while preserving public state."""

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

    clear_protected_utility_state(state)
    state[ACCESS_TOKEN_KEY] = result.access_token
    state[SESSION_ID_KEY] = result.session_id
    state[AUTH_EMAIL_KEY] = email.strip().lower()
    state[ORGANIZATION_ID_KEY] = int(organization_id)


def clear_api_session(state: MutableMapping[str, Any]) -> None:
    """Remove authentication, organization scope, and tenant-scoped utility state."""

    clear_protected_utility_state(state)
    for key in (ACCESS_TOKEN_KEY, SESSION_ID_KEY, AUTH_EMAIL_KEY, ORGANIZATION_ID_KEY):
        state.pop(key, None)
