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
        st.dataframe(fx_frame, use_container_width=True)
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
        st.dataframe(commodity_frame, use_container_width=True)
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
        st.dataframe(tax_frame, use_container_width=True)
    else:
        st.warning("No tax rules were returned for the selected jurisdictions.")


st.set_page_config(page_title="Modular Accounting Toolkit", layout="wide")
st.title("Modular Accounting Toolkit")
st.caption("Consolidated snapshots and accounting controls for FX, commodities, and tax-provider orchestration.")

health_data, health_error = _load_health()
ready_data, ready_error = _load_readiness()
providers_payload, providers_error = _load_providers()
providers_by_key = {entry["key"]: entry for entry in providers_payload if isinstance(entry, dict) and entry.get("key")}

snapshot_tab, utility_tab, plan_tab = st.tabs(["Snapshot & Controls", "Experimental Utilities", "Scenario Plans"])

with snapshot_tab:
    st.subheader("Snapshot & Controls")
    st.caption(
        "Primary flow: select provider controls, generate a consolidated snapshot, and review provenance, diagnostics,"
        " readiness, and journal controls without API schema knowledge."
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
        st.dataframe(provider_frame, use_container_width=True)

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
        st.info("Set controls and click 'Generate consolidated snapshot' to run the primary toolkit flow.")
    else:
        st.success("Snapshot generated using the selected provider controls.")
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
            st.dataframe(pd.DataFrame(provider_rows), use_container_width=True)
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
                st.dataframe(pd.DataFrame(cache_rows), use_container_width=True)

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
            st.dataframe(report_frame, use_container_width=True)

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

        with st.expander("Raw diagnostics for technical reviewers", expanded=False):
            st.json(
                {
                    "snapshot": snapshot_payload,
                    "health": health_data,
                    "readiness": ready_data,
                    "parameters": st.session_state.get("snapshot_controls_params", {}),
                }
            )

with utility_tab:
    st.subheader("Experimental Utilities")
    st.caption(
        "These features remain available for operational exploration, "
        "but the default workflow is the Snapshot & Controls"
        " accounting toolkit tab."
    )

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
            st.dataframe(preview_df, use_container_width=True)

        budget_id = st.number_input("Budget ID", min_value=1, step=1, key="budget_id_input")
        budget_horizon = st.number_input(
            "Forecast horizon (days)", min_value=1, max_value=365, value=30, key="budget_horizon_input"
        )
        budget_refresh = st.checkbox("Force refresh", value=False, key="budget_refresh_toggle")

        if st.button("Generate Budget Report", key="budget_report_button"):
            try:
                budget_params = {
                    "budget_id": int(budget_id),
                    "horizon": int(budget_horizon),
                    "refresh": budget_refresh,
                }
                response = requests.get(f"{API}/reports/budget-vs-actual", params=budget_params, timeout=60)
                response.raise_for_status()
                st.session_state["budget_report_payload"] = response.json()
                st.success("Budget report loaded")
            except Exception as exc:  # pragma: no cover - runtime feedback
                st.error(f"Failed to load budget report: {exc}")

    with cashflow_tab:
        st.markdown("#### Cashflow forecast")
        org_id = st.number_input("Organization ID", min_value=1, step=1, key="cashflow_org_input")
        cashflow_horizon = st.number_input(
            "Forecast horizon (days)", min_value=1, max_value=365, value=60, key="cashflow_horizon_input"
        )
        cashflow_refresh = st.checkbox("Force refresh", value=True, key="cashflow_refresh_toggle")

        if st.button("Generate Cashflow Forecast", key="cashflow_report_button"):
            try:
                cashflow_params = {
                    "organization_id": int(org_id),
                    "horizon": int(cashflow_horizon),
                    "refresh": cashflow_refresh,
                }
                response = requests.get(f"{API}/reports/cashflow-forecast", params=cashflow_params, timeout=60)
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
        st.markdown("#### Sync FX rates")
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

        if st.button("Sync FX Now", disabled=provider_key is None, key="fx_sync_button"):
            try:
                fx_sync_params: dict[str, Any] = {"base": base, "provider_key": provider_key}
                response = requests.post(f"{API}/fx/sync", params=fx_sync_params, timeout=30)
                response.raise_for_status()
                st.success(response.json())
            except Exception as exc:  # pragma: no cover - runtime feedback
                st.error(f"Failed to sync FX rates: {exc}")

    with market_tab:
        st.markdown("#### Sync market prices")
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

        if st.button("Sync Prices", disabled=market_provider is None, key="market_sync_button"):
            try:
                market_sync_params: dict[str, Any] = {
                    "symbol": symbol,
                    "start": start,
                    "end": end,
                    "provider_key": market_provider,
                }
                response = requests.post(f"{API}/market/sync", params=market_sync_params, timeout=30)
                response.raise_for_status()
                st.success(response.json())
            except Exception as exc:  # pragma: no cover - runtime feedback
                st.error(f"Failed to sync market prices: {exc}")

with plan_tab:
    st.subheader("Scenario Plans")
    st.caption("Upload JSON or TOML plans to validate coverage before running scenario batches.")
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
