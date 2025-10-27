"""Streamlit UI for interacting with the Modular Accounting API."""

from __future__ import annotations

import json
import os
import tomllib
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx

API = os.getenv("API_BASE", "http://localhost:8000")
BUDGET_TEMPLATE = (
    "account_id,period_start,amount\n"
    "101,2024-01-01,2500\n"
    "101,2024-02-01,2600\n"
)


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
def _load_providers() -> tuple[list[dict[str, Any]], str | None]:
    try:
        response = requests.get(f"{API}/providers", timeout=5)
        response.raise_for_status()
        payload = response.json()
        providers = payload.get("providers", []) if isinstance(payload, dict) else []
        return providers, None
    except Exception as exc:  # pragma: no cover - runtime diagnostics
        return [], str(exc)


def _provider_options(
    capability: str, providers: dict[str, dict[str, Any]]
) -> list[str]:
    return [
        key
        for key, meta in providers.items()
        if capability in meta.get("capabilities", [])
    ]


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


st.set_page_config(page_title="Modular Accounting", layout="wide")
st.title("📒 Modular Accounting Console")

health_data, health_error = _load_health()
providers_payload, providers_error = _load_providers()
providers_by_key = {
    entry["key"]: entry
    for entry in providers_payload
    if isinstance(entry, dict) and entry.get("key")
}

health_tab, budget_tab, cashflow_tab, fx_tab, market_tab, plan_tab = st.tabs(
    [
        "Health",
        "Budgets",
        "Cashflow",
        "FX Sync",
        "Market Sync",
        "Scenario Plans",
    ]
)

with health_tab:
    st.subheader("Service health & providers")
    if health_error:
        st.error(f"API not reachable at {API}: {health_error}")
        st.info("Run the API first: `uvicorn apps.api.main:app --reload`")
    elif health_data:
        st.json(health_data)

    if providers_error:
        st.error(f"Unable to load providers: {providers_error}")
    else:
        st.write(providers_payload)

with budget_tab:
    st.subheader("Upload budget lines")
    st.caption(
        "Drag & drop CSV with columns: "
        "account_id, period_start (YYYY-MM-DD), amount"
    )
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
            st.session_state["uploaded_budget_preview"] = (
                pd.read_csv(BytesIO(file_bytes)).head(100)
            )
        except Exception as exc:
            st.error(f"Failed to parse CSV: {exc}")

    stored_bytes = st.session_state.get("uploaded_budget_bytes")
    if stored_bytes and "uploaded_budget_preview" not in st.session_state:
        try:
            st.session_state["uploaded_budget_preview"] = (
                pd.read_csv(BytesIO(stored_bytes)).head(100)
            )
        except Exception as exc:
            st.error(f"Failed to parse stored CSV: {exc}")

    preview_df = st.session_state.get("uploaded_budget_preview")
    if isinstance(preview_df, pd.DataFrame):
        st.dataframe(preview_df, use_container_width=True)

    st.markdown("#### Generate budget vs actual report")
    budget_id = st.number_input(
        "Budget ID",
        min_value=1,
        step=1,
        key="budget_id_input",
    )
    budget_horizon = st.number_input(
        "Forecast horizon (days)",
        min_value=1,
        max_value=365,
        value=30,
        key="budget_horizon_input",
    )
    budget_refresh = st.checkbox(
        "Force refresh",
        value=False,
        key="budget_refresh_toggle",
    )

    if st.button("Generate Budget Report", key="budget_report_button"):
        try:
            params = {
                "budget_id": int(budget_id),
                "horizon": int(budget_horizon),
                "refresh": budget_refresh,
            }
            response = requests.get(
                f"{API}/reports/budget-vs-actual", params=params, timeout=60
            )
            response.raise_for_status()
            st.session_state["budget_report_payload"] = response.json()
            st.success("Budget report loaded")
        except Exception as exc:  # pragma: no cover - runtime feedback
            st.error(f"Failed to load budget report: {exc}")

with cashflow_tab:
    st.subheader("Cashflow forecast")
    org_id = st.number_input(
        "Organization ID",
        min_value=1,
        step=1,
        key="cashflow_org_input",
    )
    cashflow_horizon = st.number_input(
        "Forecast horizon (days)",
        min_value=1,
        max_value=365,
        value=60,
        key="cashflow_horizon_input",
    )
    cashflow_refresh = st.checkbox(
        "Force refresh",
        value=True,
        key="cashflow_refresh_toggle",
    )

    if st.button("Generate Cashflow Forecast", key="cashflow_report_button"):
        try:
            params = {
                "organization_id": int(org_id),
                "horizon": int(cashflow_horizon),
                "refresh": cashflow_refresh,
            }
            response = requests.get(
                f"{API}/reports/cashflow-forecast", params=params, timeout=60
            )
            response.raise_for_status()
            st.session_state["cashflow_report_payload"] = response.json()
            st.success("Cashflow forecast generated")
        except Exception as exc:  # pragma: no cover - runtime feedback
            st.error(f"Failed to load cashflow forecast: {exc}")

    cashflow_payload = st.session_state.get("cashflow_report_payload")
    if isinstance(cashflow_payload, dict):
        hist = pd.DataFrame(cashflow_payload.get("historical", []))
        if not hist.empty:
            hist["period"] = pd.to_datetime(hist["period"])
            hist = hist.set_index("period")
            st.line_chart(hist, use_container_width=True)
        st.metric("Current cash", f"{cashflow_payload.get('current_cash', 0):,.2f}")
        avg_flow = cashflow_payload.get("average_monthly_flow") or 0.0
        st.metric("Average monthly flow", f"{avg_flow:,.2f}")
        if _can_render_downloads() and cashflow_payload.get("csv_export"):
            st.download_button(
                "Download cashflow CSV",
                data=cashflow_payload["csv_export"],
                file_name="cashflow_forecast.csv",
                mime="text/csv",
                key="cashflow_csv_download",
            )

with fx_tab:
    st.subheader("Sync FX rates")
    base = st.text_input("Base currency", value="USD", key="fx_base_input")
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

    if st.button(
        "Sync FX Now", disabled=provider_key is None, key="fx_sync_button"
    ):
        try:
            params = {"base": base, "provider_key": provider_key}
            response = requests.post(f"{API}/fx/sync", params=params, timeout=30)
            response.raise_for_status()
            st.success(response.json())
        except Exception as exc:  # pragma: no cover - runtime feedback
            st.error(f"Failed to sync FX rates: {exc}")

with market_tab:
    st.subheader("Sync market prices")
    symbol = st.text_input("Symbol", value="AAPL", key="market_symbol_input")
    start = st.text_input("Start date", value="2024-01-01", key="market_start_input")
    end = st.text_input("End date", value="2024-12-31", key="market_end_input")
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

    if st.button(
        "Sync Prices",
        disabled=market_provider is None,
        key="market_sync_button",
    ):
        try:
            params = {
                "symbol": symbol,
                "start": start,
                "end": end,
                "provider_key": market_provider,
            }
            response = requests.post(f"{API}/market/sync", params=params, timeout=30)
            response.raise_for_status()
            st.success(response.json())
        except Exception as exc:  # pragma: no cover - runtime feedback
            st.error(f"Failed to sync market prices: {exc}")

with plan_tab:
    st.subheader("Scenario plan preview")
    st.caption("Upload JSON or TOML plans to validate coverage before execution.")
    uploaded_plan = st.file_uploader(
        "Scenario plan",
        type=["json", "toml", "tml"],
        key="scenario_plan_uploader",
        help="Preview metadata, defaults, and coverage via the API without running providers.",
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
                    response = requests.post(
                        f"{API}/snapshot/plans/preview",
                        json=parsed_plan,
                        timeout=30,
                    )
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
