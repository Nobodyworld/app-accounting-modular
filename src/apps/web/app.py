"""Streamlit UI for the modular accounting snapshot and controls experience."""

from __future__ import annotations

import json
import os
import re
import tomllib
from datetime import UTC, date, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx

from apps.api.services.snapshot_service import SnapshotOrchestrator
from apps.modular_accounting.domain import LedgerEntry, Money, Transaction
from apps.web.api_session import (
    ACCESS_TOKEN_KEY,
    AUTH_EMAIL_KEY,
    ORGANIZATION_ID_KEY,
    api_error_detail,
    auth_headers,
    authenticated_workspace_ready,
    clear_api_session,
    request_access_token,
    store_api_session,
)
from apps.web.utility_results import (
    BudgetResultView,
    CashflowResultView,
    SyncResultView,
    build_budget_result_view,
    build_cashflow_result_view,
    build_fx_sync_result_view,
    build_market_sync_result_view,
)

API = os.getenv("API_BASE", "http://localhost:8000")
BUDGET_TEMPLATE = "account_id,period_start,amount\n101,2024-01-01,2500\n101,2024-02-01,2600\n"
DEFAULT_COMMODITIES = ["XAU", "XAG", "WTI", "BRENT", "COPPER"]
DEFAULT_JURISDICTIONS = ["US", "US-CA", "GB", "DE", "FR", "JP"]
CASE_STUDY_URL = "docs/examples/foreign_currency_accounting_case_study.md"


def _can_render_downloads() -> bool:
    if os.getenv("STREAMLIT_TESTING") == "1":
        return False
    try:  # pragma: no cover - Streamlit internals
        return get_script_run_ctx() is not None
    except Exception:  # pragma: no cover - defensive
        return False


@st.cache_data(show_spinner=False)
def _load_health() -> tuple[dict[str, Any] | None, str | None]:
    try:
        response = requests.get(f"{API}/health", timeout=5)
        response.raise_for_status()
        return response.json(), None
    except Exception as exc:  # pragma: no cover - runtime diagnostics
        return None, str(exc)


@st.cache_data(show_spinner=False)
def _load_readiness() -> tuple[dict[str, Any] | None, str | None]:
    try:
        response = requests.get(f"{API}/health/ready", timeout=5)
        response.raise_for_status()
        return response.json(), None
    except Exception as exc:  # pragma: no cover - runtime diagnostics
        return None, str(exc)


@st.cache_data(show_spinner=False)
def _load_providers() -> tuple[list[dict[str, Any]], str | None]:
    try:
        response = requests.get(f"{API}/providers", timeout=5)
        response.raise_for_status()
        payload = response.json()
        providers = payload.get("providers", []) if isinstance(payload, dict) else []
        return providers, None
    except Exception as exc:  # pragma: no cover - runtime diagnostics
        return [], str(exc)


def _provider_options(capability: str, providers: dict[str, dict[str, Any]]) -> list[str]:
    return [key for key, meta in providers.items() if capability in meta.get("capabilities", [])]


def _format_provider(key: str, providers: dict[str, dict[str, Any]]) -> str:
    meta = providers.get(key, {})
    name = meta.get("name") or key
    return f"{name} ({key})" if key else name


def _parse_plan_bytes(data: bytes, name: str) -> tuple[dict[str, Any] | None, str | None]:
    suffix = Path(name).suffix.lower()
    try:
        if suffix in {".toml", ".tml"}:
            return tomllib.loads(data.decode("utf-8")), None
        return json.loads(data.decode("utf-8")), None
    except (json.JSONDecodeError, tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        return None, str(exc)


def _normalise_csv_values(raw: str) -> list[str]:
    values = [item.strip().upper() for item in raw.split(",") if item.strip()]
    return list(dict.fromkeys(values))


def _currency_error(base_currency: str) -> str | None:
    if not re.fullmatch(r"[A-Z]{3}", base_currency):
        return "Base currency must be a 3-letter ISO code such as USD or EUR."
    return None


def _format_age(seconds_value: Any) -> str:
    try:
        seconds = float(seconds_value)
    except Exception:
        return "n/a"
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    return f"{seconds / 3600:.1f}h"


def _build_snapshot(
    *,
    base_currency: str,
    commodity_symbols: list[str],
    jurisdictions: list[str],
    fx_provider_key: str,
    commodity_provider_key: str,
    tax_provider_key: str,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        orchestrator = SnapshotOrchestrator(
            fx_provider_key=fx_provider_key,
            commodity_provider_key=commodity_provider_key,
            tax_provider_key=tax_provider_key,
        )
        result = orchestrator.build_snapshot(
            base_currency=base_currency,
            commodity_symbols=commodity_symbols,
            jurisdictions=jurisdictions,
        )
        return result.as_payload(), None
    except Exception as exc:  # pragma: no cover - runtime diagnostics
        return None, str(exc)


def _journal_control_status() -> dict[str, Any]:
    amount = Money(amount=Decimal("100.00"), currency="USD")
    tx = Transaction(
        transaction_id="streamlit-control-sample",
        occurred_on=date.today(),
        description="Control sample for balanced posting check",
        entries=[
            LedgerEntry(account_code="1100", amount=amount, direction="debit"),
            LedgerEntry(account_code="4000", amount=amount, direction="credit"),
        ],
    )
    accounts = list(tx.accounts())
    return {
        "balanced": tx.is_balanced(),
        "entry_count": len(tx.entries),
        "account_count": len(set(accounts)),
        "control_name": "Balanced journal posting",
    }


def _submit_api_login() -> None:
    """Exchange sidebar credentials while keeping passwords out of retained state."""

    email = str(st.session_state.get("api_login_email", ""))
    password = str(st.session_state.get("api_login_password", ""))
    organization_id = int(st.session_state.get("api_organization_input", 0) or 0)
    result, error = request_access_token(API, email, password, post=requests.post)

    # The password widget is intentionally transient: remove its submitted value before rerendering.
    st.session_state.pop("api_login_password", None)
    if error:
        clear_api_session(st.session_state)
        st.session_state["api_login_error"] = error
        return

    if result is None:  # pragma: no cover - request_access_token always pairs this with an error
        clear_api_session(st.session_state)
        st.session_state["api_login_error"] = "Authentication response was incomplete."
        return

    store_api_session(
        st.session_state,
        result,
        email=email,
        organization_id=organization_id,
    )
    st.session_state.pop("api_login_error", None)


def _logout_api_session() -> None:
    """Clear authenticated workspace values without touching public workflow state."""

    clear_api_session(st.session_state)
    st.session_state.pop("api_login_error", None)


def _protected_response_payload(response: Any) -> tuple[Any | None, str | None]:
    """Return a safe API payload or its actionable error detail."""

    if response.status_code >= 400:
        return None, api_error_detail(response)
    try:
        return response.json(), None
    except Exception:
        return None, "API response was not valid JSON."


def _render_result_state(state: str, message: str) -> None:
    """Render a result outcome without relying on color alone."""

    if state == "success":
        st.success(message)
    elif state == "partial":
        st.warning(message)
    else:
        st.info(message)


def _render_result_metrics(metrics: tuple[tuple[str, str], ...]) -> None:
    """Render supplied presentation-model metrics without recomputation."""

    if not metrics:
        return
    for column, (label, value) in zip(st.columns(len(metrics)), metrics, strict=True):
        column.metric(label, value)


def _render_budget_result(payload: Any) -> None:
    """Render the validated budget result model for accountant review."""

    view: BudgetResultView = build_budget_result_view(payload)
    _render_result_state(view.state, view.message)
    if view.state == "empty":
        return

    _render_result_metrics(view.metrics)
    for warning in view.warnings:
        st.warning(warning)

    st.markdown("##### Report lines")
    report_rows = [{key: value for key, value in row.items() if key != "Forecast"} for row in view.rows]
    if report_rows:
        st.dataframe(pd.DataFrame(report_rows), width="stretch", hide_index=True)
        forecast_rows = [
            {"Account code": row["Account code"], "Period": row["Period"], "Forecast": row["Forecast"]}
            for row in view.rows
            if row["Forecast"]
        ]
        if forecast_rows:
            with st.expander("Forecast detail", expanded=False):
                st.dataframe(pd.DataFrame(forecast_rows), width="stretch", hide_index=True)

    with st.expander("Budget report details", expanded=False):
        st.json(view.metadata)
    if view.csv_export:
        st.download_button(
            "Download budget report CSV",
            data=view.csv_export,
            file_name="budget-vs-actual.csv",
            mime="text/csv",
            key="budget_report_download",
        )


def _render_cashflow_result(payload: Any) -> None:
    """Render the validated cashflow result model with distinct timelines."""

    view: CashflowResultView = build_cashflow_result_view(payload)
    _render_result_state(view.state, view.message)
    if view.state == "empty":
        return

    _render_result_metrics(view.metrics)
    for warning in view.warnings:
        st.warning(warning)

    st.markdown("##### Historical activity")
    if view.historical_rows:
        st.dataframe(pd.DataFrame(view.historical_rows), width="stretch", hide_index=True)
    else:
        st.info("No historical cashflow activity was returned.")

    st.markdown("##### Forecast")
    if view.forecast_rows:
        st.dataframe(pd.DataFrame(view.forecast_rows), width="stretch", hide_index=True)
    else:
        st.info("No forecast cashflow periods were returned.")

    st.caption(f"Model order: {view.model_order}. This model metadata does not guarantee forecast quality.")
    with st.expander("Forecast diagnostics", expanded=False):
        st.json(view.diagnostics)
    with st.expander("Cashflow report details", expanded=False):
        st.json(view.metadata)
    if view.csv_export:
        st.download_button(
            "Download cashflow report CSV",
            data=view.csv_export,
            file_name="cashflow-forecast.csv",
            mime="text/csv",
            key="cashflow_report_download",
        )


def _render_sync_result(view: SyncResultView, *, details_label: str) -> None:
    """Render supplied synchronization provenance without exposing raw payloads."""

    _render_result_state(view.state, view.message)
    if view.state == "empty":
        return

    count_column, provider_column, organization_column = st.columns(3)
    count_column.metric("Synced records", view.synced_count)
    provider_column.metric("Provider", view.provider or "Not provided")
    organization_column.metric("Organization ID", view.organization_id or "Not provided")
    st.caption(
        f"Provider key: {view.provider_key or 'Not provided'} · "
        f"{view.subject_label}: {view.subject_value or 'Not provided'} · "
        f"Effective range: {view.effective_range or 'Not provided'}"
    )
    with st.expander(details_label, expanded=False):
        st.json(view.technical_details)


def _render_snapshot_tables(payload: dict[str, Any]) -> None:
    fx_rows = payload.get("fx_rates", [])
    commodity_rows = payload.get("commodity_quotes", [])
    tax_rows = payload.get("tax_rules", [])

    st.markdown("#### Snapshot results")
    count_cols = st.columns(3)
    count_cols[0].metric("FX rates", len(fx_rows))
    count_cols[1].metric("Commodity quotes", len(commodity_rows))
    count_cols[2].metric("Tax rules", len(tax_rows))

    diagnostics = payload.get("diagnostics", {}) if isinstance(payload.get("diagnostics"), dict) else {}
    freshness_cols = st.columns(3)
    freshness_cols[0].metric("FX freshness", _format_age(diagnostics.get("fx_max_age_seconds")))
    freshness_cols[1].metric("Commodity freshness", _format_age(diagnostics.get("commodity_max_age_seconds")))
    freshness_cols[2].metric("Active tax rules", diagnostics.get("active_tax_rule_count", 0))

    if fx_rows:
        fx_frame = pd.DataFrame(
            [
                {
                    "Base": row.get("base_currency"),
                    "Quote": row.get("quote_currency"),
                    "Rate": row.get("rate"),
                    "As Of": row.get("as_of"),
                }
                for row in fx_rows
                if isinstance(row, dict)
            ]
        )
        st.dataframe(fx_frame, width="stretch")
    else:
        st.warning("No FX rates were returned. Check provider availability and network access.")

    if commodity_rows:
        commodity_frame = pd.DataFrame(
            [
                {
                    "Symbol": row.get("symbol"),
                    "Price": (row.get("price") or {}).get("amount") if isinstance(row, dict) else None,
                    "Currency": (row.get("price") or {}).get("currency") if isinstance(row, dict) else None,
                    "As Of": row.get("as_of") if isinstance(row, dict) else None,
                }
                for row in commodity_rows
                if isinstance(row, dict)
            ]
        )
        st.dataframe(commodity_frame, width="stretch")
    else:
        st.warning("No commodity quotes were returned for the selected symbols.")

    if tax_rows:
        tax_frame = pd.DataFrame(
            [
                {
                    "Jurisdiction": row.get("jurisdiction"),
                    "Rate": row.get("rate"),
                    "Description": row.get("description"),
                    "Effective From": row.get("effective_from"),
                    "Effective To": row.get("effective_to"),
                }
                for row in tax_rows
                if isinstance(row, dict)
            ]
        )
        st.dataframe(tax_frame, width="stretch")
    else:
        st.warning("No tax rules were returned for the selected jurisdictions.")


st.set_page_config(page_title="Modular Accounting Toolkit", layout="wide")
st.title("Modular Accounting Toolkit")
st.caption(
    "Review financial snapshots through provider evidence, journal controls, scenario plans, "
    "and optional technical diagnostics."
)

with st.sidebar:
    st.subheader("API Session")
    if st.session_state.get(ACCESS_TOKEN_KEY):
        st.success("Authenticated")
        st.write(f"Authenticated email: {st.session_state.get(AUTH_EMAIL_KEY, 'Unknown')}")
        st.write(f"Organization ID: {st.session_state.get(ORGANIZATION_ID_KEY, 'Unknown')}")
        st.caption("This organization scope applies to every protected Review Utilities request.")
        st.button("Log out", key="api_logout_button", on_click=_logout_api_session)
    else:
        st.info("Protected utilities locked")
        st.caption("Snapshot Review and Scenario Plan Preview remain public local evidence workflows.")
        login_error = st.session_state.get("api_login_error")
        if isinstance(login_error, str) and login_error:
            st.error(login_error)
        st.text_input("Email", key="api_login_email")
        st.text_input("Password", type="password", key="api_login_password")
        st.number_input("Organization ID", min_value=1, step=1, key="api_organization_input")
        st.button("Sign in", type="primary", key="api_login_button", on_click=_submit_api_login)

# Resolve the protected workspace once after the sidebar has updated the API session state.
access_token = st.session_state.get(ACCESS_TOKEN_KEY)
organization_id = st.session_state.get(ORGANIZATION_ID_KEY)
protected_ready = authenticated_workspace_ready(access_token, organization_id)
headers = auth_headers(access_token)

st.info(
    "Snapshot Review is a public/local evidence workflow. Scenario Plan Preview is public. "
    "Review Utilities require an authenticated API session and organization scope."
)

health_data, health_error = _load_health()
ready_data, ready_error = _load_readiness()
providers_payload, providers_error = _load_providers()
providers_by_key = {entry["key"]: entry for entry in providers_payload if isinstance(entry, dict) and entry.get("key")}

snapshot_tab, utility_tab, plan_tab = st.tabs(["Snapshot Review", "Review Utilities", "Scenario Plans"])

with snapshot_tab:
    st.subheader("Snapshot Review")
    st.caption(
        "Evidence-first flow: choose controlled providers, generate a financial snapshot, "
        "then review source provenance, freshness, readiness, and journal-control status."
    )
    st.info(
        "Designed review order: provider catalog → snapshot results → provenance and freshness "
        "→ readiness checks → journal-control status → technical audit payload."
    )

    if providers_error:
        st.error(f"Unable to load provider catalog from {API}/providers: {providers_error}")
        st.info("Snapshot generation is disabled until provider metadata can be loaded.")

    if providers_by_key:
        provider_frame = pd.DataFrame(
            [
                {
                    "Provider Key": key,
                    "Provider Name": meta.get("name"),
                    "Capabilities": ", ".join(meta.get("capabilities", [])),
                }
                for key, meta in sorted(providers_by_key.items())
            ]
        )
        st.dataframe(provider_frame, width="stretch")

    left, right = st.columns([3, 2])
    with left:
        base_currency = (
            st.text_input(
                "Base currency",
                value="USD",
                max_chars=3,
                help="3-letter ISO code used as the FX anchor for this snapshot.",
                key="snapshot_base_input",
            )
            .strip()
            .upper()
        )
        currency_error = _currency_error(base_currency)
        if currency_error:
            st.error(currency_error)

        default_symbols = st.multiselect(
            "Commodity symbols",
            options=DEFAULT_COMMODITIES,
            default=["XAU"],
            key="snapshot_symbols_multi",
            help="Select reference symbols or add more in the custom field.",
        )
        extra_symbols = st.text_input(
            "Additional commodity symbols (comma separated)",
            value="",
            key="snapshot_symbols_extra",
            help="Example: XPT, XPD",
        )
        commodity_symbols = list(dict.fromkeys([*default_symbols, *_normalise_csv_values(extra_symbols)]))

        default_jurisdictions = st.multiselect(
            "Jurisdictions",
            options=DEFAULT_JURISDICTIONS,
            default=["US"],
            key="snapshot_jurisdictions_multi",
            help="Used to filter tax-rule retrieval.",
        )
        extra_jurisdictions = st.text_input(
            "Additional jurisdictions (comma separated)",
            value="",
            key="snapshot_jurisdictions_extra",
            help="Example: IE, AU",
        )
        jurisdictions = list(dict.fromkeys([*default_jurisdictions, *_normalise_csv_values(extra_jurisdictions)]))

    with right:
        fx_options = _provider_options("fx", providers_by_key)
        commodity_options = _provider_options("market", providers_by_key)
        tax_options = _provider_options("tax", providers_by_key)

        fx_provider = st.selectbox(
            "FX provider",
            options=fx_options,
            index=0 if fx_options else None,
            format_func=lambda key: _format_provider(key, providers_by_key),
            key="snapshot_fx_provider_select",
            disabled=not fx_options,
        )
        commodity_provider = st.selectbox(
            "Commodity provider",
            options=commodity_options,
            index=0 if commodity_options else None,
            format_func=lambda key: _format_provider(key, providers_by_key),
            key="snapshot_commodity_provider_select",
            disabled=not commodity_options,
        )
        tax_provider = st.selectbox(
            "Tax provider",
            options=tax_options,
            index=0 if tax_options else None,
            format_func=lambda key: _format_provider(key, providers_by_key),
            key="snapshot_tax_provider_select",
            disabled=not tax_options,
        )

        missing_capabilities: list[str] = []
        if not fx_options:
            missing_capabilities.append("FX")
        if not commodity_options:
            missing_capabilities.append("Commodity")
        if not tax_options:
            missing_capabilities.append("Tax")

        if missing_capabilities:
            st.warning(f"Missing provider capabilities: {', '.join(missing_capabilities)}")

        can_generate = not currency_error and not missing_capabilities and bool(providers_by_key)
        if st.button(
            "Generate consolidated snapshot",
            key="snapshot_generate_button",
            disabled=not can_generate,
            type="primary",
        ):
            if fx_provider is None or commodity_provider is None or tax_provider is None:
                st.session_state["snapshot_controls_error"] = "Provider selection is incomplete."
                st.session_state.pop("snapshot_controls_payload", None)
            else:
                built_snapshot_payload, snapshot_error = _build_snapshot(
                    base_currency=base_currency,
                    commodity_symbols=commodity_symbols,
                    jurisdictions=jurisdictions,
                    fx_provider_key=fx_provider,
                    commodity_provider_key=commodity_provider,
                    tax_provider_key=tax_provider,
                )
                if snapshot_error:
                    st.session_state["snapshot_controls_error"] = snapshot_error
                    st.session_state.pop("snapshot_controls_payload", None)
                else:
                    st.session_state["snapshot_controls_payload"] = built_snapshot_payload
                    st.session_state.pop("snapshot_controls_error", None)
                    st.session_state["snapshot_controls_params"] = {
                        "base_currency": base_currency,
                        "commodity_symbols": commodity_symbols,
                        "jurisdictions": jurisdictions,
                        "providers": {
                            "fx": fx_provider,
                            "commodity": commodity_provider,
                            "tax": tax_provider,
                        },
                        "generated_at": datetime.now(tz=UTC).isoformat(),
                    }

    if "snapshot_controls_error" in st.session_state:
        st.error(f"Snapshot request failed: {st.session_state['snapshot_controls_error']}")
    elif "snapshot_controls_payload" not in st.session_state:
        st.info("Set provider controls and generate a consolidated snapshot to begin the accountant review flow.")
    else:
        st.success("Snapshot review generated using the selected provider controls.")
        snapshot_payload_state = st.session_state["snapshot_controls_payload"]
        if not isinstance(snapshot_payload_state, dict):
            st.error("Snapshot payload is unavailable or malformed.")
            st.stop()
        snapshot_payload: dict[str, Any] = snapshot_payload_state
        _render_snapshot_tables(snapshot_payload)

        st.markdown("#### Provider provenance")
        providers_used = snapshot_payload.get("providers", {}) if isinstance(snapshot_payload, dict) else {}
        provider_rows = []
        if isinstance(providers_used, dict):
            for capability, key in providers_used.items():
                provider_rows.append(
                    {
                        "Capability": capability,
                        "Provider Key": key,
                        "Provider Name": providers_by_key.get(str(key), {}).get("name", str(key)),
                    }
                )
        if provider_rows:
            st.dataframe(pd.DataFrame(provider_rows), width="stretch")
        else:
            st.warning("Provider provenance is not available for this run.")

        st.markdown("#### Cache and freshness diagnostics")
        cache_stats = snapshot_payload.get("cache_stats", {}) if isinstance(snapshot_payload, dict) else {}
        if isinstance(cache_stats, dict) and cache_stats:
            cache_rows: list[dict[str, Any]] = []
            for name, stats in cache_stats.items():
                if not isinstance(stats, dict):
                    continue
                cache_rows.append(
                    {
                        "Cache": name,
                        "Size": stats.get("size", 0),
                        "Hits": stats.get("hits", 0),
                        "Misses": stats.get("misses", 0),
                    }
                )
            if cache_rows:
                st.dataframe(pd.DataFrame(cache_rows), width="stretch")

        st.markdown("#### Health and readiness state")
        health_cols = st.columns(2)
        if health_data:
            health_cols[0].metric("Health status", str(health_data.get("status", "unknown")).upper())
        elif health_error:
            health_cols[0].metric("Health status", "UNAVAILABLE")
            health_cols[0].warning(f"Health endpoint unavailable: {health_error}")

        if ready_data:
            health_cols[1].metric("Readiness status", str(ready_data.get("status", "unknown")).upper())
        elif ready_error:
            health_cols[1].metric("Readiness status", "UNAVAILABLE")
            health_cols[1].warning(f"Readiness endpoint unavailable: {ready_error}")

        ready_reports = ready_data.get("reports", []) if isinstance(ready_data, dict) else []
        if ready_reports:
            report_frame = pd.DataFrame(
                [
                    {
                        "Check": row.get("name"),
                        "Healthy": row.get("healthy"),
                        "Severity": row.get("severity"),
                    }
                    for row in ready_reports
                    if isinstance(row, dict)
                ]
            )
            st.dataframe(report_frame, width="stretch")

        st.markdown("#### Journal-control status")
        journal_status = _journal_control_status()
        status_cols = st.columns(3)
        status_cols[0].metric("Control", journal_status["control_name"])
        status_cols[1].metric("Entries", journal_status["entry_count"])
        status_cols[2].metric("Unique accounts", journal_status["account_count"])
        if journal_status["balanced"]:
            st.success("Balanced journal posting control: PASS")
        else:
            st.error("Balanced journal posting control: FAIL")

        st.markdown(
            f"Reference: [{CASE_STUDY_URL}]({CASE_STUDY_URL}) "
            "- foreign-currency accounting case study and journal walkthrough."
        )

        with st.expander("Technical audit payload", expanded=False):
            st.json(
                {
                    "snapshot": snapshot_payload,
                    "health": health_data,
                    "readiness": ready_data,
                    "parameters": st.session_state.get("snapshot_controls_params", {}),
                }
            )

with utility_tab:
    st.subheader("Review Utilities")
    st.caption(
        "Budget, cashflow, FX, and market actions use the authenticated API session and its "
        "organization scope. Budget CSV preview and template behavior remain local."
    )
    if not protected_ready:
        st.warning(
            "Protected utilities locked. Sign in through API Session with a positive organization ID to continue."
        )
    else:
        st.success("Protected utilities ready for the authenticated organization scope.")

    budget_tab, cashflow_tab, fx_tab, market_tab = st.tabs(["Budgets", "Cashflow", "FX Sync", "Market Sync"])

    with budget_tab:
        st.markdown("#### Upload budget lines")
        st.caption("CSV columns: account_id, period_start (YYYY-MM-DD), amount")
        uploaded_file = st.file_uploader(
            "Budget CSV",
            type=["csv"],
            key="budget_uploader",
            help="Use the template to ensure required columns are present.",
        )

        if _can_render_downloads():
            st.download_button(
                label="Download CSV template",
                data=BUDGET_TEMPLATE,
                file_name="budget_template.csv",
                mime="text/csv",
                key="budget_template_download",
            )

        if uploaded_file is not None:
            file_bytes = uploaded_file.getvalue()
            st.session_state["uploaded_budget_bytes"] = file_bytes
            try:
                st.session_state["uploaded_budget_preview"] = pd.read_csv(BytesIO(file_bytes)).head(100)
            except Exception as exc:
                st.error(f"Failed to parse CSV: {exc}")

        stored_bytes = st.session_state.get("uploaded_budget_bytes")
        if stored_bytes and "uploaded_budget_preview" not in st.session_state:
            try:
                st.session_state["uploaded_budget_preview"] = pd.read_csv(BytesIO(stored_bytes)).head(100)
            except Exception as exc:
                st.error(f"Failed to parse stored CSV: {exc}")

        preview_df = st.session_state.get("uploaded_budget_preview")
        if isinstance(preview_df, pd.DataFrame):
            st.dataframe(preview_df, width="stretch")

        budget_id = st.number_input("Budget ID", min_value=1, step=1, key="budget_id_input")
        budget_horizon = st.number_input(
            "Forecast horizon (days)", min_value=1, max_value=365, value=30, key="budget_horizon_input"
        )
        budget_refresh = st.checkbox("Force refresh", value=False, key="budget_refresh_toggle")

        if st.button("Generate Budget Report", key="budget_report_button", disabled=not protected_ready):
            try:
                budget_params = {
                    "budget_id": int(budget_id),
                    "organization_id": int(organization_id),
                    "horizon": int(budget_horizon),
                    "refresh": budget_refresh,
                }
                with st.spinner("Generating budget report..."):
                    response = requests.get(
                        f"{API}/reports/budget-vs-actual",
                        params=budget_params,
                        headers=headers,
                        timeout=60,
                    )
            except requests.RequestException as exc:  # pragma: no cover - runtime feedback
                budget_payload, budget_error = None, f"Budget service unavailable: {exc}"
            except Exception:  # pragma: no cover - defensive UI boundary
                budget_payload, budget_error = None, "Budget report request could not be completed."
            else:
                budget_payload, budget_error = _protected_response_payload(response)

            if budget_error:
                st.session_state.pop("budget_report_payload", None)
                st.session_state["budget_report_error"] = budget_error
            else:
                st.session_state["budget_report_payload"] = budget_payload
                st.session_state.pop("budget_report_error", None)

        budget_error = st.session_state.get("budget_report_error")
        if isinstance(budget_error, str) and budget_error:
            st.error(f"Budget report unavailable: {budget_error}")
        budget_payload = st.session_state.get("budget_report_payload")
        if budget_payload is not None:
            _render_budget_result(budget_payload)

    with cashflow_tab:
        st.markdown("#### Cashflow forecast")
        st.caption("Uses the organization scope selected in API Session.")
        cashflow_horizon = st.number_input(
            "Forecast horizon (days)", min_value=1, max_value=365, value=60, key="cashflow_horizon_input"
        )
        cashflow_refresh = st.checkbox("Force refresh", value=True, key="cashflow_refresh_toggle")

        if st.button("Generate Cashflow Forecast", key="cashflow_report_button", disabled=not protected_ready):
            try:
                cashflow_params = {
                    "organization_id": int(organization_id),
                    "horizon": int(cashflow_horizon),
                    "refresh": cashflow_refresh,
                }
                with st.spinner("Generating cashflow forecast..."):
                    response = requests.get(
                        f"{API}/reports/cashflow-forecast",
                        params=cashflow_params,
                        headers=headers,
                        timeout=60,
                    )
            except requests.RequestException as exc:  # pragma: no cover - runtime feedback
                cashflow_payload, cashflow_error = None, f"Cashflow service unavailable: {exc}"
            except Exception:  # pragma: no cover - defensive UI boundary
                cashflow_payload, cashflow_error = None, "Cashflow forecast request could not be completed."
            else:
                cashflow_payload, cashflow_error = _protected_response_payload(response)

            if cashflow_error:
                st.session_state.pop("cashflow_report_payload", None)
                st.session_state["cashflow_report_error"] = cashflow_error
            else:
                st.session_state["cashflow_report_payload"] = cashflow_payload
                st.session_state.pop("cashflow_report_error", None)

        cashflow_error = st.session_state.get("cashflow_report_error")
        if isinstance(cashflow_error, str) and cashflow_error:
            st.error(f"Cashflow forecast unavailable: {cashflow_error}")

        cashflow_payload = st.session_state.get("cashflow_report_payload")
        if cashflow_payload is not None:
            _render_cashflow_result(cashflow_payload)

    with fx_tab:
        st.markdown("#### Sync FX rates")
        base = st.text_input("Base currency", value="USD", key="fx_base_input")
        normalized_base = base.strip().upper()
        fx_currency_error = _currency_error(normalized_base)
        if fx_currency_error:
            st.error(fx_currency_error)
        fx_options = _provider_options("fx", providers_by_key)
        provider_key = None
        if fx_options:
            provider_key = st.selectbox(
                "FX provider",
                options=fx_options,
                format_func=lambda key: _format_provider(key, providers_by_key),
                key="fx_provider_select",
            )
        else:
            st.info("No FX providers configured on the API")

        can_sync_fx = protected_ready and provider_key is not None and fx_currency_error is None
        if st.button("Sync FX Now", disabled=not can_sync_fx, key="fx_sync_button"):
            try:
                fx_sync_params: dict[str, Any] = {
                    "organization_id": int(organization_id),
                    "base": normalized_base,
                    "provider_key": provider_key,
                }
                with st.spinner("Synchronizing FX rates..."):
                    response = requests.post(f"{API}/fx/sync", params=fx_sync_params, headers=headers, timeout=30)
            except requests.RequestException as exc:  # pragma: no cover - runtime feedback
                fx_error = f"FX service unavailable: {exc}"
            except Exception:  # pragma: no cover - defensive UI boundary
                fx_error = "FX synchronization request could not be completed."
            else:
                fx_payload, fx_error = _protected_response_payload(response)

            if fx_error:
                st.session_state.pop("fx_sync_payload", None)
                st.session_state["fx_sync_error"] = fx_error
            else:
                st.session_state["fx_sync_payload"] = fx_payload
                st.session_state.pop("fx_sync_error", None)

        fx_error = st.session_state.get("fx_sync_error")
        if isinstance(fx_error, str) and fx_error:
            st.error(f"FX synchronization unavailable: {fx_error}")
        fx_payload = st.session_state.get("fx_sync_payload")
        if fx_payload is not None:
            _render_sync_result(
                build_fx_sync_result_view(fx_payload, organization_id=int(organization_id)),
                details_label="FX synchronization details",
            )

    with market_tab:
        st.markdown("#### Sync market prices")
        symbol = st.text_input("Symbol", value="AAPL", key="market_symbol_input")
        normalized_symbol = symbol.strip().upper()
        start = st.date_input("Start date", value=date(2024, 1, 1), key="market_start_input")
        end = st.date_input("End date", value=date(2024, 12, 31), key="market_end_input")
        market_date_error = "Start date must be on or before end date." if start > end else None
        if not normalized_symbol:
            st.error("Market symbol is required.")
        if market_date_error:
            st.error(market_date_error)
        market_options = _provider_options("market", providers_by_key)
        market_provider = None
        if market_options:
            market_provider = st.selectbox(
                "Market provider",
                options=market_options,
                format_func=lambda key: _format_provider(key, providers_by_key),
                key="market_provider_select",
            )
        else:
            st.info("No market providers configured on the API")

        can_sync_market = (
            protected_ready and market_provider is not None and bool(normalized_symbol) and not market_date_error
        )
        if st.button("Sync Prices", disabled=not can_sync_market, key="market_sync_button"):
            try:
                market_sync_params: dict[str, Any] = {
                    "organization_id": int(organization_id),
                    "symbol": normalized_symbol,
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "provider_key": market_provider,
                }
                with st.spinner("Synchronizing market prices..."):
                    response = requests.post(
                        f"{API}/market/sync", params=market_sync_params, headers=headers, timeout=30
                    )
            except requests.RequestException as exc:  # pragma: no cover - runtime feedback
                market_error = f"Market service unavailable: {exc}"
            except Exception:  # pragma: no cover - defensive UI boundary
                market_error = "Market synchronization request could not be completed."
            else:
                market_payload, market_error = _protected_response_payload(response)

            if market_error:
                st.session_state.pop("market_sync_payload", None)
                st.session_state["market_sync_error"] = market_error
            else:
                st.session_state["market_sync_payload"] = market_payload
                st.session_state.pop("market_sync_error", None)

        market_error = st.session_state.get("market_sync_error")
        if isinstance(market_error, str) and market_error:
            st.error(f"Market synchronization unavailable: {market_error}")
        market_payload = st.session_state.get("market_sync_payload")
        if market_payload is not None:
            _render_sync_result(
                build_market_sync_result_view(market_payload, organization_id=int(organization_id)),
                details_label="Market synchronization details",
            )

with plan_tab:
    st.subheader("Scenario Plan Review")
    st.caption("Upload JSON or TOML plans to review scenario coverage before running scenario batches.")
    uploaded_plan = st.file_uploader(
        "Scenario plan",
        type=["json", "toml", "tml"],
        key="scenario_plan_uploader",
        help="Preview metadata, defaults, and coverage via the API before running scenarios.",
    )

    if uploaded_plan is not None:
        try:
            st.session_state["scenario_plan_bytes"] = uploaded_plan.getvalue()
            st.session_state["scenario_plan_name"] = uploaded_plan.name
        except Exception as exc:
            st.error(f"Failed to read uploaded file: {exc}")

    stored_plan = st.session_state.get("scenario_plan_bytes")
    stored_plan_name = st.session_state.get("scenario_plan_name", "scenario_plan.json")

    if st.button("Preview plan", key="scenario_plan_preview_button"):
        if not stored_plan:
            st.warning("Upload a scenario plan before requesting a preview.")
        else:
            parsed_plan, error = _parse_plan_bytes(stored_plan, stored_plan_name)
            if error:
                st.error(f"Plan parsing failed: {error}")
            elif not isinstance(parsed_plan, dict):
                st.error("Scenario plans must define a JSON or TOML object.")
            else:
                try:
                    response = requests.post(f"{API}/snapshot/plans/preview", json=parsed_plan, timeout=30)
                    response.raise_for_status()
                except Exception as exc:  # pragma: no cover - runtime feedback
                    st.error(f"Failed to preview plan: {exc}")
                else:
                    st.session_state["scenario_plan_preview"] = response.json()
                    st.success("Plan preview generated")

    preview_payload = st.session_state.get("scenario_plan_preview")
    if isinstance(preview_payload, dict):
        summary = preview_payload.get("summary", {})
        metadata = preview_payload.get("plan", {}).get("metadata", {})
        cols = st.columns(3)
        cols[0].metric("Scenarios", summary.get("scenario_count", 0))
        cols[1].metric("Base currencies", len(summary.get("base_currencies", [])))
        cols[2].metric("Tags", len(summary.get("tags", [])))
        with st.expander("Plan metadata", expanded=True):
            st.json(metadata)
        with st.expander("Coverage summary", expanded=True):
            st.json(summary)
    else:
        st.info("Upload a plan to preview metadata and coverage details.")
