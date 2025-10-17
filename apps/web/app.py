import os
import json
from io import BytesIO

import pandas as pd
import requests
import streamlit as st
from streamlit.runtime.scriptrunner import get_script_run_ctx

import requests
import streamlit as st

API = os.getenv("API_BASE", "http://localhost:8000")
BUDGET_TEMPLATE = """account_id,period_start,amount\n101,2024-01-01,2500\n101,2024-02-01,2600\n"""


def _can_render_downloads() -> bool:
    if os.getenv("STREAMLIT_TESTING") == "1":
        return False
    try:
        return get_script_run_ctx() is not None
    except Exception:  # pragma: no cover - defensive
        return False


st.set_page_config(page_title="Modular Accounting", layout="wide")
st.title("📒 Modular Accounting (ModAcct)")
# todo - fix
tabs = st.tabs(["Health", "Budgets", "Reports", "FX Sync", "Market Sync", "Forecast"])

with tabs[0]:
    st.subheader("Service health & plugins")
    try:
        r = requests.get(f"{API}/health", timeout=5)
        st.write(r.json())
        p = requests.get(f"{API}/providers", timeout=5).json()
        st.write(p)
    except Exception as e:
        st.error(f"API not reachable at {API}: {e}")
health_data: dict[str, object] | None = None
health_error: str | None = None
providers_payload: list[dict[str, object]] = []
providers_error: str | None = None

try:
    health_response = requests.get(f"{API}/health", timeout=5)
    health_response.raise_for_status()
    health_data = health_response.json()
except Exception as exc:  # pragma: no cover - Streamlit runtime
    health_error = str(exc)

try:
    providers_response = requests.get(f"{API}/providers", timeout=5)
    providers_response.raise_for_status()
    payload = providers_response.json()
    providers_payload = payload.get("providers", []) if isinstance(payload, dict) else []
except Exception as exc:  # pragma: no cover - Streamlit runtime
    providers_error = str(exc)

providers_by_key = {
    entry["key"]: entry
    for entry in providers_payload
    if isinstance(entry, dict) and entry.get("key")
}


def _provider_options(capability: str) -> list[str]:
    return [
        key
        for key, meta in providers_by_key.items()
        if capability in meta.get("capabilities", [])
    ]


def _format_provider(key: str) -> str:
    meta = providers_by_key.get(key, {})
    name = meta.get("name") or key
    return f"{name} ({key})" if key else name


tab1, tab2, tab3, tab4 = st.tabs(["Health", "FX Sync", "Market Sync", "Forecast"])

with tab1:
    st.subheader("Service health & providers")
    if health_data:
        st.json(health_data)
    if health_error:
        st.error(f"API not reachable at {API}: {health_error}")
        st.info("Run the API first: `uvicorn apps.api.main:app --reload`")
    if providers_error:
        st.error(f"Unable to load providers: {providers_error}")
    else:
        st.write(providers_payload)

with tabs[1]:
    st.subheader("Upload budget lines")
    st.caption("Drag & drop CSV with columns: account_id, period_start (YYYY-MM-DD), amount")
    uploaded_file = st.file_uploader(
        "Budget CSV",
        type=["csv"],
        key="budget_uploader",
        help="Use the template to ensure required columns are present.",
    )

    col_template, _ = st.columns(2)
    with col_template:
        if _can_render_downloads():
            st.download_button(
                label="Download CSV template",
                data=BUDGET_TEMPLATE,
                file_name="budget_template.csv",
                mime="text/csv",
                key="budget_template_download",
            )

    preview = st.session_state.get("uploaded_budget_preview")
    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()
        st.session_state["uploaded_budget_bytes"] = file_bytes
        preview = pd.read_csv(BytesIO(file_bytes)).head(100)
        st.session_state["uploaded_budget_preview"] = preview
    elif preview is None and st.session_state.get("uploaded_budget_bytes"):
        file_bytes = st.session_state["uploaded_budget_bytes"]
        preview = pd.read_csv(BytesIO(file_bytes)).head(100)
        st.session_state["uploaded_budget_preview"] = preview

    if preview is not None:
        st.success("Budget file parsed successfully.")
        st.dataframe(preview, use_container_width=True)
        st.info(
            "Use the API to persist budgets and then generate reports from the Reports tab."
        )
    else:
        st.info("No budget uploaded yet.")

with tabs[2]:
    st.subheader("Automated reporting")
    st.caption("Generate variance analysis and cashflow forecasts directly from the API.")

    col_budget, col_cashflow = st.columns(2)

    with col_budget:
        st.markdown("#### Budget vs Actual")
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
            value=90,
            step=1,
            key="budget_horizon_input",
        )
        budget_refresh = st.checkbox(
            "Force refresh",
            value=True,
            key="budget_refresh_toggle",
        )

        if st.button("Generate Budget vs Actual", use_container_width=True, key="budget_report_button"):
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
                st.success("Budget report generated.")
            except Exception as exc:  # pragma: no cover - UI feedback
                st.error(f"Failed to load budget report: {exc}")

        budget_payload = st.session_state.get("budget_report_payload")
        if budget_payload:
            df_budget = pd.DataFrame(budget_payload["lines"])
            if not df_budget.empty:
                df_budget["period_start"] = pd.to_datetime(df_budget["period_start"])
                chart_data = df_budget.set_index("period_start")[
                    ["budget_amount", "actual_amount"]
                ]
                st.line_chart(chart_data, use_container_width=True)
                variance_view = df_budget[["account_name", "period_start", "variance", "burn_rate"]].copy()
                variance_view["burn_rate"] = variance_view["burn_rate"].fillna(0.0)
                st.dataframe(variance_view, use_container_width=True)
                summary = budget_payload.get("summary", {})
                st.metric("Total variance", f"{summary.get('total_variance', 0):,.2f}")
                st.metric("Burn rate", f"{summary.get('burn_rate', 0):.2f}")
            if _can_render_downloads():
                st.download_button(
                    "Download variance CSV",
                    data=budget_payload.get("csv_export", ""),
                    file_name="budget_vs_actual.csv",
                    mime="text/csv",
                    key="budget_csv_download",
                )

    with col_cashflow:
        st.markdown("#### Cashflow forecast")
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

        if st.button("Generate Cashflow Forecast", use_container_width=True, key="cashflow_report_button"):
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
                st.success("Cashflow forecast generated.")
            except Exception as exc:  # pragma: no cover - UI feedback
                st.error(f"Failed to load cashflow forecast: {exc}")

        cashflow_payload = st.session_state.get("cashflow_report_payload")
        if cashflow_payload:
            hist_df = pd.DataFrame(cashflow_payload["historical"])
            if not hist_df.empty:
                hist_df["period"] = pd.to_datetime(hist_df["period"])
                hist_df = hist_df.set_index("period")
                st.line_chart(hist_df, use_container_width=True)
            forecast_points = cashflow_payload.get("forecast", [])
            if forecast_points:
                forecast_df = pd.DataFrame(forecast_points, columns=["period", "amount"])
                forecast_df["period"] = pd.to_datetime(forecast_df["period"])
                forecast_df = forecast_df.set_index("period")
                st.area_chart(forecast_df, use_container_width=True)
            st.metric("Current cash", f"{cashflow_payload.get('current_cash', 0):,.2f}")
            st.metric(
                "Average monthly flow",
                f"{cashflow_payload.get('average_monthly_flow', 0) or 0:,.2f}",
            )
            if _can_render_downloads():
                st.download_button(
                    "Download cashflow CSV",
                    data=cashflow_payload.get("csv_export", ""),
                    file_name="cashflow_forecast.csv",
                    mime="text/csv",
                    key="cashflow_csv_download",
                )

with tabs[3]:
    st.subheader("Sync FX Rates")
    # todo - fix
    base = st.text_input("Base currency", value="USD", key="fx_base_input")
    provider = st.text_input(
        "Provider module",
        value="plugins.fx_ecb.provider",
        key="fx_provider_input",
    )
    if st.button("Sync FX Now", key="fx_sync_button"):
        try:
            r = requests.post(
                f"{API}/fx/sync",
                params={"base": base, "provider": provider},
    base = st.text_input("Base currency", value="USD")
    fx_options = _provider_options("fx")
    if fx_options:
        provider_key = st.selectbox(
            "FX Provider",
            options=fx_options,
            format_func=_format_provider,
        )
        selected_meta = providers_by_key.get(provider_key)
        if selected_meta and selected_meta.get("description"):
            st.caption(selected_meta["description"])
    else:
        st.selectbox("FX Provider", options=["No providers available"], disabled=True)
        provider_key = None
        st.warning("No FX providers configured; update the server allowlist to continue.")

    if st.button("Sync Now", disabled=provider_key is None):
        try:
            r = requests.post(
                f"{API}/fx/sync",
                params={"base": base, "provider_key": provider_key},
                timeout=30,
            )
            st.success(r.json())
        except Exception as e:
            st.error(str(e))

with tabs[4]:
    st.subheader("Sync Market Prices")
    # todo - fix
    symbol = st.text_input("Symbol", value="AAPL", key="market_symbol_input")
    start = st.text_input(
        "Start (YYYY-MM-DD)", value="2024-01-01", key="market_start_input"
    )
    end = st.text_input(
        "End (YYYY-MM-DD)", value="2024-12-31", key="market_end_input"
    )
    provider = st.text_input(
        "Provider module",
        value="plugins.market_yfinance.provider",
        key="market_provider_input",
    )
    if st.button("Fetch Prices", key="market_fetch_button"):
    symbol = st.text_input("Symbol", value="AAPL")
    start = st.text_input("Start (YYYY-MM-DD)", value="2024-01-01")
    end = st.text_input("End (YYYY-MM-DD)", value="2024-12-31")
    market_options = _provider_options("market")
    if market_options:
        market_provider_key = st.selectbox(
            "Market Data Provider",
            options=market_options,
            format_func=_format_provider,
        )
        selected_meta = providers_by_key.get(market_provider_key)
        if selected_meta and selected_meta.get("description"):
            st.caption(selected_meta["description"])
    else:
        st.selectbox(
            "Market Data Provider", options=["No providers available"], disabled=True
        )
        market_provider_key = None
        st.warning(
            "No market data providers configured; update the server allowlist to continue."
        )

    if st.button("Fetch Prices", disabled=market_provider_key is None):
        try:
            r = requests.post(
                f"{API}/market/sync",
                params={
                    "symbol": symbol,
                    "start": start,
                    "end": end,
                  # todo - fix
                    "provider": provider,
                    "provider_key": market_provider_key,
                },
                timeout=60,
            )
            st.success(r.json())
        except Exception as e:
            st.error(str(e))

with tabs[5]:
    st.subheader("Forecast Demo")
    st.caption("Paste time series as JSON array of [timestamp, value] pairs.")
    default_series = json.dumps(
        [
            ["2024-01-01", 100],
            ["2024-01-02", 101],
            ["2024-01-03", 103],
            ["2024-01-04", 102],
            ["2024-01-05", 104],
        ]
    )
    series = st.text_area("Series", value=default_series, height=150, key="forecast_series_input")
    horizon = st.number_input(
        "Horizon (days)", value=30, min_value=1, max_value=365, key="forecast_horizon_input"
    )
    if st.button("Forecast", key="forecast_button"):
        try:
            payload = {"series": json.loads(series), "horizon": int(horizon)}
            r = requests.post(f"{API}/forecast/series", json=payload, timeout=60)
            out = r.json()
            st.write(out)
        except Exception as e:
            st.error(str(e))

