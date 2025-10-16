import streamlit as st
import requests
import os

API = os.getenv("API_BASE", "http://localhost:8000")

st.set_page_config(page_title="Modular Accounting", layout="wide")
st.title("📒 Modular Accounting (ModAcct)")

tab1, tab2, tab3, tab4 = st.tabs(["Health", "FX Sync", "Market Sync", "Forecast"])

with tab1:
    st.subheader("Service health & plugins")
    try:
        r = requests.get(f"{API}/health", timeout=5)
        st.write(r.json())
        p = requests.get(f"{API}/providers", timeout=5).json()
        st.write(p)
    except Exception as e:
        st.error(f"API not reachable at {API}: {e}")
        st.info("Run the API first: `uvicorn apps.api.main:app --reload`")

with tab2:
    st.subheader("Sync FX Rates")
    base = st.text_input("Base currency", value="USD")
    provider = st.text_input("Provider module", value="plugins.fx_ecb.provider")
    if st.button("Sync Now"):
        try:
            r = requests.post(f"{API}/fx/sync", params={"base": base, "provider": provider}, timeout=30)
            st.success(r.json())
        except Exception as e:
            st.error(str(e))

with tab3:
    st.subheader("Sync Market Prices")
    symbol = st.text_input("Symbol", value="AAPL")
    start = st.text_input("Start (YYYY-MM-DD)", value="2024-01-01")
    end = st.text_input("End (YYYY-MM-DD)", value="2024-12-31")
    provider = st.text_input("Provider module", value="plugins.market_yfinance.provider")
    if st.button("Fetch Prices"):
        try:
            r = requests.post(f"{API}/market/sync", params={"symbol": symbol, "start": start, "end": end, "provider": provider}, timeout=60)
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
