import os

import requests
import streamlit as st

API = os.getenv("API_BASE", "http://localhost:8000")

st.set_page_config(page_title="Modular Accounting", layout="wide")
st.title("📒 Modular Accounting (ModAcct)")

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

with tab2:
    st.subheader("Sync FX Rates")
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

with tab3:
    st.subheader("Sync Market Prices")
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
                    "provider_key": market_provider_key,
                },
                timeout=60,
            )
            st.success(r.json())
        except Exception as e:
            st.error(str(e))

with tab4:
    st.subheader("Forecast Demo")
    st.caption("Paste time series as JSON array of [timestamp, value] pairs.")
    default_series = '[["2024-01-01",100],["2024-01-02",101],["2024-01-03",103],["2024-01-04",102],["2024-01-05",104]]'
    series = st.text_area("Series", value=default_series, height=150)
    horizon = st.number_input("Horizon (days)", value=30, min_value=1, max_value=365)
    if st.button("Forecast"):
        try:
            import json
            payload = {"series": json.loads(series), "horizon": int(horizon)}
            r = requests.post(f"{API}/forecast/series", json=payload, timeout=60)
            out = r.json()
            st.write(out)
        except Exception as e:
            st.error(str(e))
