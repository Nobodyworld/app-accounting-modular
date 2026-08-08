"""Authenticated Streamlit accountant close workspace."""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import pandas as pd
import requests
import streamlit as st

from apps.web.api_session import (
    ORGANIZATION_ID_KEY,
    api_error_detail,
    authenticated_workspace_ready,
    request_with_one_refresh,
)

_CYCLE_STATE_KEYS = (
    "close_cycle_payload",
    "close_readiness",
    "close_reconciliations",
    "close_variances",
    "close_approvals",
    "close_checklist",
    "close_evidence_preview",
    "close_evidence_result",
)


def _clear_cycle_state() -> None:
    for key in _CYCLE_STATE_KEYS:
        st.session_state.pop(key, None)


def _clear_all_close_state() -> None:
    for key in list(st.session_state):
        if key.startswith("close_"):
            st.session_state.pop(key, None)


def _safe_json(response: requests.Response) -> tuple[Any | None, str | None]:
    if response.status_code >= 400:
        return None, api_error_detail(response)
    try:
        return response.json(), None
    except Exception:
        return None, "The close service returned an invalid response."


def _request(
    method: str,
    path: str,
    *,
    params: Mapping[str, Any] | None = None,
    json_body: Mapping[str, Any] | None = None,
    timeout: int = 30,
) -> tuple[requests.Response | None, str | None]:
    request_call = {"GET": requests.get, "POST": requests.post, "PATCH": requests.patch}.get(method.upper())
    if request_call is None:
        return None, "The close request method is unsupported."
    try:
        response, session_error = request_with_one_refresh(
            st.session_state,
            _api_base(),
            lambda headers: request_call(
                f"{_api_base().rstrip('/')}{path}",
                params=dict(params or {}),
                json=dict(json_body) if json_body is not None else None,
                headers=headers,
                timeout=timeout,
            ),
            post=requests.post,
        )
    except requests.RequestException:
        return None, "The close service is unavailable. Try again when the API is reachable."
    except Exception:
        return None, "The close request could not be completed."
    if session_error:
        _clear_cycle_state()
        return None, session_error
    if response is not None and response.status_code in {403, 404} and st.session_state.get("close_selected_cycle_id"):
        _clear_all_close_state()
    return response, None


def _api_base() -> str:
    return os.getenv("API_BASE", "http://localhost:8000")


def _org_params() -> dict[str, int]:
    return {"organization_id": int(st.session_state[ORGANIZATION_ID_KEY])}


def _load_json(key: str, path: str) -> Any | None:
    response, error = _request("GET", path, params=_org_params())
    if error:
        st.session_state["close_error"] = error
        return None
    if response is None:
        st.session_state["close_error"] = "The close request did not return a response."
        return None
    payload, payload_error = _safe_json(response)
    if payload_error:
        st.session_state["close_error"] = payload_error
        return None
    st.session_state[key] = payload
    st.session_state.pop("close_error", None)
    return payload


def _mutate(
    method: str,
    path: str,
    body: Mapping[str, Any] | None,
    *,
    success: str,
    timeout: int = 30,
) -> Any | None:
    response, error = _request(method, path, params=_org_params(), json_body=body, timeout=timeout)
    if error:
        st.session_state["close_error"] = error
        return None
    if response is None:
        st.session_state["close_error"] = "The close request did not return a response."
        return None
    payload, payload_error = _safe_json(response)
    if payload_error:
        st.session_state["close_error"] = payload_error
        return None
    st.session_state["close_confirmation"] = success
    st.session_state.pop("close_error", None)
    return payload


def _refresh_periods() -> list[dict[str, Any]]:
    payload = _load_json("close_periods", "/close/periods")
    return payload if isinstance(payload, list) else []


def _refresh_cycles(period_id: int) -> list[dict[str, Any]]:
    payload = _load_json("close_cycles", f"/close/periods/{period_id}/cycles")
    return payload if isinstance(payload, list) else []


def _selected_cycle_id() -> int | None:
    try:
        value = int(st.session_state.get("close_selected_cycle_id", 0) or 0)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _refresh_cycle_data(cycle_id: int) -> None:
    _load_json("close_cycle_payload", f"/close/cycles/{cycle_id}")
    _load_json("close_readiness", f"/close/cycles/{cycle_id}/readiness")


def _currency(value: Any) -> str:
    try:
        return f"{Decimal(str(value)):,.2f}"
    except (InvalidOperation, TypeError, ValueError):
        return "—"


def _render_selection() -> int | None:
    periods = st.session_state.get("close_periods")
    if not isinstance(periods, list):
        periods = _refresh_periods()
    with st.expander("Create accounting period", expanded=not periods):
        with st.form("close_period_create_form"):
            period_label = st.text_input("Period label", max_chars=120, placeholder="March 2026")
            columns = st.columns(2)
            start_date = columns[0].date_input("Inclusive start date", value=date.today().replace(day=1))
            end_date = columns[1].date_input("Inclusive end date", value=date.today())
            create_period = st.form_submit_button("Create period", type="primary")
        if create_period:
            created = _mutate(
                "POST",
                "/close/periods",
                {"label": period_label, "start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
                success="Accounting period created.",
            )
            if created:
                periods = _refresh_periods()

    if not periods:
        st.info("Create an accounting period to begin the close workflow.")
        return None
    period_options = {int(item["id"]): item for item in periods if isinstance(item, Mapping) and item.get("id")}
    period_ids = list(period_options)
    default_period = int(st.session_state.get("close_selected_period_id", period_ids[0]))
    if default_period not in period_options:
        default_period = period_ids[0]
    selected_period = st.selectbox(
        "Accounting period",
        period_ids,
        index=period_ids.index(default_period),
        format_func=lambda item_id: f"{period_options[item_id].get('label')} · {period_options[item_id].get('status')}",
        key="close_period_selector",
    )
    if st.session_state.get("close_selected_period_id") != selected_period:
        st.session_state["close_selected_period_id"] = selected_period
        st.session_state.pop("close_selected_cycle_id", None)
        st.session_state.pop("close_cycles", None)
        _clear_cycle_state()

    cycles = st.session_state.get("close_cycles")
    if not isinstance(cycles, list):
        cycles = _refresh_cycles(selected_period)
    if not cycles:
        with st.form("close_cycle_create_form"):
            st.markdown("#### Start the controlled close")
            cycle_name = st.text_input(
                "Close cycle name", value=f"{period_options[selected_period].get('label')} Close"
            )
            owner_id = st.number_input("Owner user ID", min_value=1, step=1)
            due_date = st.date_input("Due date", value=date.today())
            policy_override = st.checkbox(
                "Apply administrator policy override",
                value=False,
                help="Ledger managers use server defaults. Overrides require an administrator and an audit reason.",
            )
            variance_required = True
            approval_mode = "REQUESTED_ONLY"
            policy_reason = ""
            if policy_override:
                variance_required = st.checkbox("Require a period-scoped variance review run", value=True)
                approval_mode = st.selectbox(
                    "Journal approval scope",
                    ["REQUESTED_ONLY", "ALL_PERIOD_TRANSACTIONS"],
                    help=(
                        "Requested only requires approval for explicit requests; "
                        "all period transactions covers every journal."
                    ),
                )
                policy_reason = st.text_input("Policy override reason")
            create_cycle = st.form_submit_button("Create close cycle", type="primary")
        if create_cycle:
            create_payload: dict[str, Any] = {
                "name": cycle_name,
                "owner_user_id": int(owner_id),
                "due_date": due_date.isoformat(),
            }
            if policy_override:
                create_payload["policy"] = {
                    "variance_review_required": variance_required,
                    "journal_approval_mode": approval_mode,
                    "reason": policy_reason,
                }
            created = _mutate(
                "POST",
                f"/close/periods/{selected_period}/cycles",
                create_payload,
                success="Close cycle created with the standard eight-control checklist.",
            )
            if isinstance(created, Mapping):
                cycles = _refresh_cycles(selected_period)
                st.session_state["close_selected_cycle_id"] = int(created["id"])
        if not cycles:
            return None

    cycle_options = {int(item["id"]): item for item in cycles if isinstance(item, Mapping) and item.get("id")}
    cycle_ids = list(cycle_options)
    default_cycle = int(st.session_state.get("close_selected_cycle_id", cycle_ids[0]))
    if default_cycle not in cycle_options:
        default_cycle = cycle_ids[0]
    selected_cycle = st.selectbox(
        "Close cycle",
        cycle_ids,
        index=cycle_ids.index(default_cycle),
        format_func=lambda item_id: f"{cycle_options[item_id].get('name')} · {cycle_options[item_id].get('status')}",
        key="close_cycle_selector",
    )
    if st.session_state.get("close_selected_cycle_id") != selected_cycle:
        st.session_state["close_selected_cycle_id"] = selected_cycle
        _clear_cycle_state()
    if not isinstance(st.session_state.get("close_cycle_payload"), Mapping):
        _refresh_cycle_data(selected_cycle)
    return selected_cycle


def _render_overview(cycle_id: int) -> None:
    readiness = st.session_state.get("close_readiness")
    cycle = st.session_state.get("close_cycle_payload")
    if not isinstance(readiness, Mapping) or not isinstance(cycle, Mapping):
        _refresh_cycle_data(cycle_id)
        readiness = st.session_state.get("close_readiness", {})
        cycle = st.session_state.get("close_cycle_payload", {})
    title = str(cycle.get("name") or "Close cycle")
    st.markdown(f"### {title}")
    controls = st.columns([2, 1, 1])
    controls[0].caption(f"Owner user {cycle.get('owner_user_id', '—')} · Due {cycle.get('due_date') or 'not set'}")
    policy = cycle.get("policy", {}) if isinstance(cycle.get("policy"), Mapping) else {}
    required_accounts = policy.get("required_reconciliation_account_ids", [])
    st.caption(
        f"Required reconciliation accounts: {len(required_accounts) if isinstance(required_accounts, list) else 0} · "
        f"Variance review: {'required' if policy.get('variance_review_required', True) else 'not required'} · "
        f"Journal approval mode: {policy.get('journal_approval_mode', 'REQUESTED_ONLY')}"
    )
    if readiness.get("latest_variance_run_id") is not None:
        st.caption(
            f"Latest variance run {readiness.get('latest_variance_run_id')} · "
            f"{readiness.get('latest_variance_run_row_count', 0)} in-period row(s)"
        )
    if controls[1].button("Refresh readiness", key="close_refresh_readiness"):
        _refresh_cycle_data(cycle_id)
        readiness = st.session_state.get("close_readiness", {})
    status_value = str(readiness.get("state") or "NOT_STARTED")
    blocker_count = int(readiness.get("blocker_count", 0) or 0)
    completed = int(readiness.get("completed_required_count", 0) or 0)
    required = int(readiness.get("required_task_count", 0) or 0)
    if status_value == "BLOCKED":
        st.warning(
            f"Readiness: {status_value} — {completed} of {required} required controls complete; "
            f"{blocker_count} blockers."
        )
    elif status_value in {"READY_FOR_APPROVAL", "CLOSED"}:
        st.success(f"Readiness: {status_value} — {completed} of {required} required controls complete.")
    else:
        st.info(f"Readiness: {status_value} — {completed} of {required} required controls complete.")
    metric_columns = st.columns(2)
    metric_columns[0].metric("Required controls", f"{completed} / {required}")
    metric_columns[1].metric("Open blockers", blocker_count)
    blockers = readiness.get("blockers", [])
    if isinstance(blockers, list) and blockers:
        st.markdown("#### Blockers")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Control": item.get("category"),
                        "Blocker": item.get("message"),
                        "Next action": item.get("recommended_action"),
                        "Reference": f"{item.get('source_entity_type')}:{item.get('source_entity_id')}",
                        "Code": item.get("code"),
                    }
                    for item in blockers
                    if isinstance(item, Mapping)
                ]
            ),
            width="stretch",
            hide_index=True,
        )
        staged_blocker = next(
            (item for item in blockers if isinstance(item, Mapping) and item.get("code") == "STAGED_ITEMS_UNRESOLVED"),
            None,
        )
        if isinstance(staged_blocker, Mapping) and str(staged_blocker.get("source_entity_id", "")).isdigit():
            staged_id = int(staged_blocker["source_entity_id"])
            if st.button("Process next staged journal", key="close_process_staged"):
                processed = _mutate(
                    "POST",
                    "/workflow/process",
                    {"staged_ids": [staged_id], "auto_post": True},
                    success=f"Staged journal {staged_id} processed through the existing workflow service.",
                )
                if processed:
                    _refresh_cycle_data(cycle_id)
    else:
        st.success("No server-derived blockers remain.")
    status_now = str(cycle.get("status") or "")
    version = int(cycle.get("version", 1) or 1)
    if status_now == "DRAFT" and st.button("Start close cycle", type="primary", key="close_start_cycle"):
        updated = _mutate(
            "POST", f"/close/cycles/{cycle_id}/start", {"version": version}, success="Close cycle started."
        )
        if updated:
            _refresh_cycle_data(cycle_id)
    elif status_now in {"IN_PROGRESS", "BLOCKED"} and blocker_count == 0:
        if st.button("Mark ready for approval", type="primary", key="close_mark_ready"):
            updated = _mutate(
                "POST", f"/close/cycles/{cycle_id}/ready", {"version": version}, success="Cycle marked ready."
            )
            if updated:
                _refresh_cycle_data(cycle_id)
    elif status_now == "READY_FOR_APPROVAL":
        with st.form("close_return_to_work_form"):
            reason = st.text_area("Return-to-work reason", max_chars=1000)
            return_to_work = st.form_submit_button("Return cycle to work")
        if return_to_work:
            updated = _mutate(
                "POST",
                f"/close/cycles/{cycle_id}/return-to-work",
                {"version": version, "reason": reason},
                success="Cycle returned to work; prior evidence is stale.",
            )
            if updated:
                _refresh_cycle_data(cycle_id)
    elif status_now == "CANCELLED":
        st.info("This cancelled cycle is read-only until an administrator restarts it.")
        with st.form("close_restart_form"):
            reason = st.text_area("Restart reason", max_chars=1000)
            restart = st.form_submit_button("Restart cancelled cycle", type="primary")
        if restart:
            updated = _mutate(
                "POST",
                f"/close/cycles/{cycle_id}/restart",
                {"version": version, "reason": reason},
                success="Cancelled cycle restarted with its prior audit history intact.",
            )
            if updated:
                _refresh_cycle_data(cycle_id)
    if status_now in {"DRAFT", "IN_PROGRESS", "BLOCKED"}:
        with st.form("close_cancel_form"):
            reason = st.text_area("Cancellation reason", max_chars=1000)
            cancel = st.form_submit_button("Cancel close cycle")
        if cancel:
            updated = _mutate(
                "POST",
                f"/close/cycles/{cycle_id}/cancel",
                {"version": version, "reason": reason},
                success="Close cycle cancelled; the accounting period remains open.",
            )
            if updated:
                _refresh_cycle_data(cycle_id)


def _render_reconciliations(cycle_id: int, *, mutable: bool) -> None:
    st.markdown("#### Account reconciliations")
    st.caption("Difference = control balance − ledger ending balance. Ledger balance is calculated by the API.")
    rows = _load_json("close_reconciliations", f"/close/cycles/{cycle_id}/reconciliations") or []
    with st.form("close_reconciliation_form"):
        columns = st.columns(2)
        account_id = columns[0].number_input("Account ID", min_value=1, step=1)
        control_balance = columns[1].text_input("Control or statement balance", value="0.00")
        tolerance = columns[0].text_input("Tolerance", value="0.00")
        notes = columns[1].text_area("Notes or exception explanation", max_chars=4096)
        prepare = st.form_submit_button("Prepare reconciliation", type="primary", disabled=not mutable)
    if prepare:
        existing = next(
            (row for row in rows if isinstance(row, Mapping) and int(row.get("account_id", 0) or 0) == int(account_id)),
            None,
        )
        prepared = _mutate(
            "PATCH" if isinstance(existing, Mapping) else "POST",
            (
                f"/close/cycles/{cycle_id}/reconciliations/{existing['id']}"
                if isinstance(existing, Mapping)
                else f"/close/cycles/{cycle_id}/reconciliations"
            ),
            {
                "account_id": int(account_id),
                "control_balance": control_balance,
                "tolerance": tolerance,
                "notes": notes,
                "evidence_metadata": {},
                "version": existing.get("version") if isinstance(existing, Mapping) else None,
            },
            success="Reconciliation prepared with a server-calculated ledger balance.",
        )
        if prepared:
            rows = _load_json("close_reconciliations", f"/close/cycles/{cycle_id}/reconciliations") or []
            _refresh_cycle_data(cycle_id)
    if isinstance(rows, list) and rows:
        display = pd.DataFrame(
            [
                {
                    "ID": row.get("id"),
                    "Account": row.get("account_id"),
                    "Ledger ending": _currency(row.get("ledger_ending_balance")),
                    "Control": _currency(row.get("control_balance")),
                    "Difference": _currency(row.get("difference")),
                    "Tolerance": _currency(row.get("tolerance")),
                    "Status": row.get("status"),
                    "Prepared by": row.get("prepared_by_id"),
                    "Approved by": row.get("approved_by_id"),
                }
                for row in rows
                if isinstance(row, Mapping)
            ]
        )
        st.dataframe(display, width="stretch", hide_index=True)
        with st.form("close_reconciliation_approval_form"):
            approval_id = st.selectbox(
                "Reconciliation to approve",
                [int(row["id"]) for row in rows if isinstance(row, Mapping) and row.get("id")],
            )
            selected = next(row for row in rows if int(row["id"]) == approval_id)
            approve = st.form_submit_button("Approve independently", disabled=not mutable)
        if approve:
            result = _mutate(
                "POST",
                f"/close/cycles/{cycle_id}/reconciliations/{approval_id}/approve",
                {"version": int(selected["version"])},
                success="Reconciliation independently approved.",
            )
            if result:
                _load_json("close_reconciliations", f"/close/cycles/{cycle_id}/reconciliations")
                _refresh_cycle_data(cycle_id)
    else:
        st.info("No reconciliations have been prepared for this cycle.")


def _render_variances(cycle_id: int, *, mutable: bool) -> None:
    st.markdown("#### Budget variance review")
    st.caption("Rows are materialized from the existing BudgetService report; the UI does not recalculate actuals.")
    with st.form("close_variance_generate_form"):
        columns = st.columns(2)
        budget_id = columns[0].number_input("Budget ID", min_value=1, step=1)
        horizon = columns[1].number_input("Forecast horizon", min_value=1, max_value=365, value=30)
        absolute = columns[0].text_input("Absolute materiality threshold", value="1000.00")
        percentage = columns[1].text_input("Percentage threshold", value="0.10")
        generate = st.form_submit_button("Generate variance reviews", type="primary", disabled=not mutable)
    if generate:
        result = _mutate(
            "POST",
            f"/close/cycles/{cycle_id}/variance-reviews/from-budget",
            {
                "budget_id": int(budget_id),
                "horizon": int(horizon),
                "absolute_threshold": absolute,
                "percentage_threshold": percentage,
                "refresh": True,
            },
            success="Variance review rows generated from the budget report.",
            timeout=60,
        )
        if isinstance(result, list):
            st.session_state["close_variances"] = result
            _refresh_cycle_data(cycle_id)
    rows = _load_json("close_variances", f"/close/cycles/{cycle_id}/variance-reviews") or []
    material_only = st.checkbox("Show material variances only", value=True, key="close_material_only")
    visible = (
        [row for row in rows if not material_only or bool(row.get("is_material"))] if isinstance(rows, list) else []
    )
    if visible:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "ID": row.get("id"),
                        "Account": row.get("account_id"),
                        "Period": row.get("period_start"),
                        "Budget": _currency(row.get("budget_amount")),
                        "Actual": _currency(row.get("actual_amount")),
                        "Variance": _currency(row.get("variance_amount")),
                        "Material": "Yes" if row.get("is_material") else "No",
                        "Disposition": row.get("disposition"),
                    }
                    for row in visible
                ]
            ),
            width="stretch",
            hide_index=True,
        )
        with st.form("close_variance_update_form"):
            review_id = st.selectbox("Variance review", [int(row["id"]) for row in visible])
            disposition = st.selectbox(
                "Disposition", ["EXPLAINED", "TIMING", "PERMANENT", "CORRECTION_REQUIRED", "ACCEPTED"]
            )
            note = st.text_area("Reviewer note", max_chars=4096)
            update = st.form_submit_button("Record disposition", disabled=not mutable)
        if update:
            selected = next(row for row in visible if int(row["id"]) == review_id)
            result = _mutate(
                "PATCH",
                f"/close/cycles/{cycle_id}/variance-reviews/{review_id}",
                {"version": int(selected["version"]), "disposition": disposition, "note": note},
                success="Variance disposition recorded.",
            )
            if result:
                _load_json("close_variances", f"/close/cycles/{cycle_id}/variance-reviews")
                _refresh_cycle_data(cycle_id)
    else:
        st.info("No variance review rows match the current filter.")


def _render_approvals(cycle_id: int, *, mutable: bool) -> None:
    st.markdown("#### Journal approvals")
    st.caption("Requestors cannot approve their own requests. A second authenticated user must decide them.")
    with st.form("close_approval_request_form"):
        reference_type = st.radio(
            "Journal reference type", ["Posted transaction", "Staged transaction"], horizontal=True
        )
        reference_id = st.number_input("Journal reference ID", min_value=1, step=1)
        reason = st.text_area("Request comment", max_chars=2000)
        request_approval = st.form_submit_button("Request approval", type="primary", disabled=not mutable)
    if request_approval:
        body = {
            "transaction_id": int(reference_id) if reference_type == "Posted transaction" else None,
            "staged_transaction_id": int(reference_id) if reference_type == "Staged transaction" else None,
            "reason": reason,
        }
        result = _mutate(
            "POST",
            f"/close/cycles/{cycle_id}/journal-approvals",
            body,
            success="Journal approval requested.",
        )
        if result:
            _refresh_cycle_data(cycle_id)
    rows = _load_json("close_approvals", f"/close/cycles/{cycle_id}/journal-approvals") or []
    if isinstance(rows, list) and rows:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "ID": row.get("id"),
                        "Posted": row.get("transaction_id"),
                        "Staged": row.get("staged_transaction_id"),
                        "Requestor": row.get("requestor_user_id"),
                        "Status": row.get("status"),
                        "Decided by": row.get("decided_by_id"),
                        "History": len(row.get("history", [])),
                    }
                    for row in rows
                    if isinstance(row, Mapping)
                ]
            ),
            width="stretch",
            hide_index=True,
        )
        with st.form("close_approval_decision_form"):
            approval_id = st.selectbox("Approval request", [int(row["id"]) for row in rows])
            decision = st.selectbox("Decision", ["APPROVED", "REJECTED", "REVOKED"])
            comment = st.text_area("Decision comment", max_chars=2000)
            decide = st.form_submit_button("Record independent decision", disabled=not mutable)
        if decide:
            selected = next(row for row in rows if int(row["id"]) == approval_id)
            result = _mutate(
                "POST",
                f"/close/cycles/{cycle_id}/journal-approvals/{approval_id}/decide",
                {"version": int(selected["version"]), "decision": decision, "reason": comment},
                success="Journal approval decision recorded.",
            )
            if result:
                _load_json("close_approvals", f"/close/cycles/{cycle_id}/journal-approvals")
                _refresh_cycle_data(cycle_id)
    else:
        st.info("No journal approval requests exist for this cycle.")


def _render_checklist(cycle_id: int, *, operational: bool, configurable: bool) -> None:
    st.markdown("#### Close checklist")
    rows = _load_json("close_checklist", f"/close/cycles/{cycle_id}/checklist") or []
    if isinstance(rows, list):
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Task": row.get("title"),
                        "Category": row.get("category"),
                        "Control": row.get("control_type"),
                        "Required": "Yes" if row.get("required") else "No",
                        "Status": row.get("status"),
                        "Owner": row.get("owner_user_id"),
                        "Due": row.get("due_date"),
                    }
                    for row in rows
                    if isinstance(row, Mapping)
                ]
            ),
            width="stretch",
            hide_index=True,
        )
    with st.form("close_custom_task_form"):
        columns = st.columns(2)
        title = columns[0].text_input("Custom task title", max_chars=200)
        owner = columns[1].number_input("Owner user ID", min_value=1, step=1)
        required = columns[0].checkbox("Required task")
        due = columns[1].date_input("Task due date", value=date.today())
        create = st.form_submit_button("Add custom task", disabled=not configurable)
    if create:
        result = _mutate(
            "POST",
            f"/close/cycles/{cycle_id}/checklist",
            {
                "title": title,
                "description": "Accountant-defined close task.",
                "category": "custom",
                "required": required,
                "owner_user_id": int(owner),
                "due_date": due.isoformat(),
            },
            success="Custom checklist task added.",
        )
        if result:
            _load_json("close_checklist", f"/close/cycles/{cycle_id}/checklist")
            _refresh_cycle_data(cycle_id)
    manual = (
        [row for row in rows if row.get("control_type") != "SYSTEM" and row.get("task_key") != "final_close_approved"]
        if isinstance(rows, list)
        else []
    )
    if manual:
        with st.form("close_task_update_form"):
            task_id = st.selectbox("Manual task", [int(row["id"]) for row in manual])
            complete = st.checkbox("Mark complete")
            notes = st.text_area("Completion note", max_chars=2000)
            update = st.form_submit_button("Update task", disabled=not operational)
        if update:
            selected = next(row for row in manual if int(row["id"]) == task_id)
            result = _mutate(
                "PATCH",
                f"/close/cycles/{cycle_id}/checklist/{task_id}",
                {
                    "version": int(selected["version"]),
                    "complete": complete,
                    "notes": notes,
                    "owner_user_id": selected.get("owner_user_id"),
                    "due_date": selected.get("due_date"),
                },
                success="Checklist task updated.",
            )
            if result:
                _load_json("close_checklist", f"/close/cycles/{cycle_id}/checklist")
                _refresh_cycle_data(cycle_id)


def _render_evidence_and_close(cycle_id: int) -> None:
    st.markdown("#### Evidence and final close")
    st.warning(
        "Early Beta · Portfolio Preview. Evidence supports review but is not a production close certification, "
        "public-hosting approval, or regulatory compliance statement."
    )
    preview = _load_json("close_evidence_preview", f"/close/cycles/{cycle_id}/evidence/preview") or {}
    cycle = st.session_state.get("close_cycle_payload", {})
    readiness = st.session_state.get("close_readiness", {})
    status_value = str(cycle.get("status") or "")
    version = int(cycle.get("version", 1) or 1)
    columns = st.columns(2)
    columns[0].metric("Evidence freshness", preview.get("freshness", "MISSING"))
    columns[1].metric("Source revision", preview.get("source_revision", preview.get("source_version", "—")))
    if preview.get("latest_manifest_sha256"):
        st.code(str(preview["latest_manifest_sha256"]), language=None)
    evidence_mutable = status_value not in {"CLOSED", "CANCELLED"}
    if st.button(
        "Generate draft evidence",
        type="primary",
        key="close_generate_evidence",
        disabled=not evidence_mutable,
    ):
        result = _mutate(
            "POST",
            f"/close/cycles/{cycle_id}/evidence",
            None,
            success="Deterministic draft close evidence generated and audited.",
            timeout=60,
        )
        if isinstance(result, Mapping):
            st.session_state["close_evidence_result"] = result
            _load_json("close_evidence_preview", f"/close/cycles/{cycle_id}/evidence/preview")
            _refresh_cycle_data(cycle_id)
            preview = st.session_state.get("close_evidence_preview", preview)
    result = st.session_state.get("close_evidence_result")
    if isinstance(result, Mapping):
        st.caption("Manifest SHA-256")
        st.code(str(result.get("manifest_sha256")), language=None)
    if isinstance(preview, Mapping) and preview.get("freshness") == "CURRENT":
        response, error = _request(
            "GET", f"/close/cycles/{cycle_id}/evidence/download", params=_org_params(), timeout=60
        )
        if error:
            st.caption(error)
        elif response is not None and response.status_code < 400 and response.content:
            filename = "close-evidence.zip"
            disposition = response.headers.get("Content-Disposition", "")
            if "filename=" in disposition:
                filename = disposition.split("filename=", 1)[1].strip('"')
            st.download_button(
                "Download evidence ZIP",
                data=response.content,
                file_name=filename,
                mime="application/zip",
                key="close_evidence_download",
            )
    else:
        st.caption("Generate current evidence before downloading the ZIP.")
    if status_value == "READY_FOR_APPROVAL":
        if st.button("Close accounting period", type="primary", key="close_final_action"):
            updated = _mutate(
                "POST", f"/close/cycles/{cycle_id}/close", {"version": version}, success="Period closed atomically."
            )
            if updated:
                _refresh_periods()
                _refresh_cycle_data(cycle_id)
    elif status_value == "CLOSED":
        with st.expander("Verify the closed-period posting control"):
            with st.form("close_posting_lock_verification_form"):
                verification_date = st.date_input("Posting date inside the closed period", value=date.today())
                posting_columns = st.columns(2)
                debit_account = posting_columns[0].number_input("Debit account ID", min_value=1, step=1)
                credit_account = posting_columns[1].number_input("Credit account ID", min_value=1, step=1)
                amount = st.text_input("Verification amount", value="1.00")
                verify_lock = st.form_submit_button("Verify posting is rejected")
            if verify_lock:
                response, request_error = _request(
                    "POST",
                    "/ledger/post",
                    params=None,
                    json_body={
                        "organization_id": int(st.session_state[ORGANIZATION_ID_KEY]),
                        "date": verification_date.isoformat(),
                        "description": "Closed-period posting control verification",
                        "source": "streamlit-close-verification",
                        "postings": [
                            {"account_id": int(debit_account), "debit": amount, "credit": "0"},
                            {"account_id": int(credit_account), "debit": "0", "credit": amount},
                        ],
                    },
                )
                if request_error:
                    st.error(request_error)
                elif response is not None and response.status_code == 409:
                    st.success("Posting rejected by the centralized closed-period guard; no journal was created.")
                elif response is not None:
                    st.error("Posting was not rejected as expected. Do not rely on this close state.")
        with st.form("close_reopen_form"):
            reason = st.text_area("Reopen reason", max_chars=1000)
            reopen = st.form_submit_button("Reopen period")
        if reopen:
            updated = _mutate(
                "POST",
                f"/close/cycles/{cycle_id}/reopen",
                {"version": version, "reason": reason},
                success="Period explicitly reopened; prior evidence is stale.",
            )
            if updated:
                _refresh_periods()
                _refresh_cycle_data(cycle_id)
    elif readiness.get("blocker_count", 0):
        st.info("Final close remains unavailable until all server-derived blockers are resolved.")


def render_close_workspace(*, access_token: str | None, organization_id: int | None) -> None:
    """Render the complete controlled close workflow."""

    st.markdown(
        """
        <style>
        [data-testid="stMetric"] {border: 1px solid #d9e0ea; padding: .85rem 1rem; border-radius: .35rem;}
        div[data-testid="stDataFrame"] {border: 1px solid #d9e0ea;}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.subheader("Close Workspace")
    st.caption("Period administration, reconciliations, variance review, approvals, checklist, and close evidence.")
    if not authenticated_workspace_ready(access_token, organization_id):
        st.warning("Close Workspace locked. Sign in through API Session with a positive organization ID.")
        return
    confirmation = st.session_state.pop("close_confirmation", None)
    if isinstance(confirmation, str) and confirmation:
        st.success(confirmation)
    error = st.session_state.pop("close_error", None)
    if isinstance(error, str) and error:
        st.error(error)
    cycle_id = _render_selection()
    if cycle_id is None:
        return
    cycle = st.session_state.get("close_cycle_payload", {})
    cycle_status = str(cycle.get("status") or "") if isinstance(cycle, Mapping) else ""
    operational = cycle_status in {"IN_PROGRESS", "BLOCKED"}
    configurable = cycle_status in {"DRAFT", "IN_PROGRESS", "BLOCKED"}
    if cycle_status in {"READY_FOR_APPROVAL", "CLOSED", "CANCELLED"}:
        st.info(
            f"{cycle_status.replace('_', ' ').title()} is read-only for operational records. "
            "Use the explicit lifecycle action in Overview or Evidence & close."
        )
    tabs = st.tabs(
        ["Overview", "Reconciliations", "Variance review", "Journal approvals", "Checklist", "Evidence & close"]
    )
    with tabs[0]:
        _render_overview(cycle_id)
    with tabs[1]:
        _render_reconciliations(cycle_id, mutable=operational)
    with tabs[2]:
        _render_variances(cycle_id, mutable=operational)
    with tabs[3]:
        _render_approvals(cycle_id, mutable=operational)
    with tabs[4]:
        _render_checklist(cycle_id, operational=operational, configurable=configurable)
    with tabs[5]:
        _render_evidence_and_close(cycle_id)


__all__ = ["render_close_workspace"]
