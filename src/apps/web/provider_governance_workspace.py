"""Streamlit provider-governance workspace backed only by authoritative API state."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Any, cast

import requests
import streamlit as st

from apps.provider_sdk import SUPPORTED_CAPABILITIES
from apps.web.api_session import (
    api_error_detail,
    authenticated_workspace_ready,
    request_with_one_refresh,
)


def _request_json(
    state: MutableMapping[str, Any],
    api_base: str,
    request: Any,
) -> tuple[dict[str, Any] | None, str | None, int | None]:
    response, session_error = request_with_one_refresh(state, api_base, request, post=cast(Any, requests.post))
    if session_error:
        return None, session_error, None
    if response is None:
        return None, "Provider governance service returned no response.", None
    if response.status_code >= 400:
        return None, api_error_detail(response), response.status_code
    try:
        payload = response.json()
    except Exception:
        return None, "Provider governance response was not valid JSON.", response.status_code
    if not isinstance(payload, dict):
        return None, "Provider governance response was malformed.", response.status_code
    return payload, None, response.status_code


def _catalog(
    state: MutableMapping[str, Any], api_base: str, organization_id: int
) -> tuple[dict[str, Any] | None, str | None]:
    payload, error, _ = _request_json(
        state,
        api_base,
        lambda headers: requests.get(
            f"{api_base.rstrip('/')}/providers",
            params={"organization_id": organization_id},
            headers=headers,
            timeout=15,
        ),
    )
    return payload, error


def _policies(
    state: MutableMapping[str, Any], api_base: str, organization_id: int
) -> tuple[dict[str, Any] | None, str | None]:
    payload, error, _ = _request_json(
        state,
        api_base,
        lambda headers: requests.get(
            f"{api_base.rstrip('/')}/providers/policies",
            params={"organization_id": organization_id},
            headers=headers,
            timeout=15,
        ),
    )
    return payload, error


def _pinned_revision(
    state: MutableMapping[str, Any],
    *,
    state_key: str,
    item_key: str,
    current_revision: Any,
) -> int:
    """Pin the revision presented to an editor until its mutation completes."""

    revisions = state.get(state_key)
    if not isinstance(revisions, dict):
        revisions = {}
        state[state_key] = revisions
    if item_key not in revisions:
        revisions[item_key] = int(current_revision or 0)
    return int(revisions[item_key])


def render_provider_governance_workspace(
    *,
    api_base: str,
    access_token: str | None,
    organization_id: int | None,
    state: MutableMapping[str, Any] | None = None,
) -> None:
    """Render the protected member/admin provider governance experience."""

    session_state = cast(MutableMapping[str, Any], state if state is not None else st.session_state)
    st.subheader("Provider Governance")
    st.caption(
        "Organization policy narrows the operator process allowlist. It cannot add modules, "
        "install packages, or store provider credentials."
    )
    if not authenticated_workspace_ready(access_token, organization_id):
        st.warning("Provider Governance is locked. Sign in and select an organization.")
        return
    org_id = int(organization_id or 0)
    catalog_payload, catalog_error = _catalog(session_state, api_base, org_id)
    if catalog_error:
        session_state.pop("provider_governance_catalog", None)
        st.error(f"Provider catalog unavailable: {catalog_error}")
        return
    assert catalog_payload is not None
    session_state["provider_governance_catalog"] = catalog_payload
    providers_raw = catalog_payload.get("providers", [])
    providers = [item for item in providers_raw if isinstance(item, Mapping)] if isinstance(providers_raw, list) else []
    can_manage = bool(catalog_payload.get("can_manage"))

    if not providers:
        st.info("No provider registration evidence is available.")
        return
    rows = [
        {
            "Provider": item.get("name") or item.get("provider_key"),
            "Key": item.get("provider_key"),
            "Capabilities": ", ".join(str(value) for value in item.get("capabilities", [])),
            "Enabled": "Enabled" if item.get("enabled") else "Disabled",
            "Effective defaults": ", ".join(str(value) for value in item.get("default_capabilities", [])) or "—",
            "Provider / SDK": f"{item.get('provider_version') or 'unknown'} / {item.get('sdk_version') or 'unknown'}",
            "Compatibility": str((item.get("compatibility") or {}).get("status", "unknown")).upper(),
            "Conformance": "PASS" if item.get("conforming") else "FAIL",
            "Credentials": "READY" if item.get("credential_ready") else "NOT READY",
            "Effective": "YES" if item.get("effective") else "NO",
            "Source": item.get("source"),
            "Next action": item.get("next_action"),
        }
        for item in providers
    ]
    st.dataframe(rows, width="stretch", hide_index=True)
    st.caption("Credential readiness reports environment-variable presence only; it does not validate remote access.")

    provider_keys = [str(item.get("provider_key")) for item in providers]
    selected_key = st.selectbox(
        "Provider detail",
        provider_keys,
        key="provider_governance_detail_select",
        format_func=lambda key: next(
            (f"{item.get('name')} ({key})" for item in providers if item.get("provider_key") == key), key
        ),
    )
    selected = next(item for item in providers if item.get("provider_key") == selected_key)
    credential_rows = selected.get("credential_requirements", [])
    if credential_rows:
        st.dataframe(
            [
                {"Configuration name": row.get("name"), "Present": "YES" if row.get("present") else "NO"}
                for row in credential_rows
                if isinstance(row, Mapping)
            ],
            width="stretch",
            hide_index=True,
        )
    with st.expander("Bounded technical information", expanded=False):
        st.json(
            {
                "configuration_fingerprint": selected.get("configuration_fingerprint"),
                "manifest_fingerprint": selected.get("manifest_fingerprint"),
                "lifecycle_status": selected.get("lifecycle_status"),
                "registration_revision": selected.get("registration_revision"),
                "policy_revision": selected.get("policy_revision"),
                "blocked_reasons": selected.get("blocked_reasons"),
                "checks": (selected.get("technical") or {}).get("checks", []),
            }
        )

    confirmation = session_state.pop("provider_governance_confirmation", None)
    if isinstance(confirmation, str):
        st.success(confirmation)
    conflict = session_state.pop("provider_governance_conflict", None)
    if isinstance(conflict, str):
        st.warning(f"Revision conflict: {conflict} The catalog was refreshed; review and retry.")
    mutation_error = session_state.pop("provider_governance_error", None)
    if isinstance(mutation_error, str):
        st.error(mutation_error)

    if not can_manage:
        st.info("Read-only organization member view. An organization administrator manages policy and defaults.")
        return

    st.markdown("#### Administrator controls")
    policy_revisions_key = "provider_governance_policy_edit_revisions"
    policy_revision = _pinned_revision(
        session_state,
        state_key=policy_revisions_key,
        item_key=selected_key,
        current_revision=selected.get("policy_revision"),
    )
    policy_enabled = st.checkbox(
        "Provider enabled for this organization",
        value=bool(selected.get("enabled")),
        key="provider_governance_policy_enabled",
    )
    policy_note = st.text_area(
        "Administrative reason or note",
        value=str(selected.get("policy_note") or ""),
        max_chars=1_000,
        key="provider_governance_policy_note",
    )
    if st.button("Save provider policy", type="primary", key="provider_governance_policy_save"):
        mutation_payload, error, response_status = _request_json(
            session_state,
            api_base,
            lambda headers: requests.put(
                f"{api_base.rstrip('/')}/providers/{selected_key}/policy",
                params={"organization_id": org_id},
                json={
                    "enabled": policy_enabled,
                    "note": policy_note,
                    "revision": policy_revision,
                },
                headers=headers,
                timeout=15,
            ),
        )
        if error:
            key = "provider_governance_conflict" if response_status == 409 else "provider_governance_error"
            session_state[key] = error
            if response_status == 409:
                cast(dict[str, int], session_state[policy_revisions_key]).pop(selected_key, None)
        else:
            assert mutation_payload is not None
            cast(dict[str, int], session_state[policy_revisions_key])[selected_key] = int(
                mutation_payload.get("revision", policy_revision)
            )
            session_state["provider_governance_confirmation"] = f"Policy saved for {selected_key}."
        st.rerun()

    policies_payload, policies_error = _policies(session_state, api_base, org_id)
    if policies_error:
        st.error(f"Capability defaults unavailable: {policies_error}")
        return
    assert policies_payload is not None
    defaults_raw = policies_payload.get("defaults", [])
    defaults = [item for item in defaults_raw if isinstance(item, Mapping)] if isinstance(defaults_raw, list) else []
    default_by_capability = {str(item.get("capability")): item for item in defaults}
    capability = st.selectbox(
        "Capability",
        list(SUPPORTED_CAPABILITIES),
        key="provider_governance_default_capability",
    )
    candidates = [
        str(item.get("provider_key"))
        for item in providers
        if item.get("effective") and capability in item.get("capabilities", [])
    ]
    current_default = default_by_capability.get(capability)
    default_revisions_key = "provider_governance_default_edit_revisions"
    default_revision = _pinned_revision(
        session_state,
        state_key=default_revisions_key,
        item_key=capability,
        current_revision=current_default.get("revision") if current_default else 0,
    )
    if candidates:
        default_index = (
            candidates.index(str(current_default.get("provider_key")))
            if current_default is not None and str(current_default.get("provider_key")) in candidates
            else 0
        )
        default_key = st.selectbox(
            "Default provider",
            candidates,
            index=default_index,
            key="provider_governance_default_provider",
        )
        if st.button("Set capability default", key="provider_governance_default_set"):
            mutation_payload, error, response_status = _request_json(
                session_state,
                api_base,
                lambda headers: requests.put(
                    f"{api_base.rstrip('/')}/providers/defaults/{capability}",
                    params={"organization_id": org_id},
                    json={
                        "provider_key": default_key,
                        "revision": default_revision,
                    },
                    headers=headers,
                    timeout=15,
                ),
            )
            if error:
                key = "provider_governance_conflict" if response_status == 409 else "provider_governance_error"
                session_state[key] = error
                if response_status == 409:
                    cast(dict[str, int], session_state[default_revisions_key]).pop(capability, None)
            else:
                assert mutation_payload is not None
                cast(dict[str, int], session_state[default_revisions_key])[capability] = int(
                    mutation_payload.get("revision", default_revision)
                )
                session_state["provider_governance_confirmation"] = f"Default for {capability} set to {default_key}."
            st.rerun()
    else:
        st.info(f"No effective {capability} provider is available for default selection.")

    if current_default is not None and st.button("Clear capability default", key="provider_governance_default_clear"):
        mutation_payload, error, response_status = _request_json(
            session_state,
            api_base,
            lambda headers: requests.delete(
                f"{api_base.rstrip('/')}/providers/defaults/{capability}",
                params={
                    "organization_id": org_id,
                    "revision": default_revision,
                },
                headers=headers,
                timeout=15,
            ),
        )
        if error:
            key = "provider_governance_conflict" if response_status == 409 else "provider_governance_error"
            session_state[key] = error
            if response_status == 409:
                cast(dict[str, int], session_state[default_revisions_key]).pop(capability, None)
        else:
            assert mutation_payload is not None
            cast(dict[str, int], session_state[default_revisions_key])[capability] = int(
                mutation_payload.get("revision", default_revision)
            )
            session_state["provider_governance_confirmation"] = f"Default for {capability} cleared."
        st.rerun()
