# Modular Accounting (ModAcct)

An extensible, **portable** accounting platform with a plugin system for **tax rules**, **FX**, **market data**, **commodities**, and **event-aware forecasting**.

- Backend: **FastAPI** + **SQLModel** (SQLite by default for zero-setup portability)
- UI: **Streamlit** (lightweight) + **OpenAPI docs** at `/docs`
- Plugins: Drop-in modules for data providers and tax rules
- Forecasting: Basic ARIMA via statsmodels (pluggable)
- CLI: `python -m cli.macli` for imports, syncs, and reports
- Docker: `docker-compose up` for a two-service dev stack

> Use `# TODO` markers inside code to highlight expansion points.

## Quickstart

```bash
# 1) Python env
pip install -r requirements.txt
cp .env.example .env

# 2) Run API
uvicorn apps.api.main:app --reload

# 3) Run UI
streamlit run apps/web/app.py
```

Open the API docs at <http://localhost:8000/docs> and the UI at <http://localhost:8501>.

## Key Ideas

- **Modularity first**: Everything is a provider or plugin with a clear interface.
- **Portable**: SQLite by default, swap to Postgres by changing `DATABASE_URL`.
- **Auditable**: Double-entry ledger primitives, typed models, and versioned ETL runs.
- **Global-aware**: Country + jurisdiction taxonomy for tax rules, rates, and regulatory data.
- **Event-informed**: Optional event-feeds (e.g., GDELT/NewsAPI) to nudge forecasts (# TODO advanced ML).

## Features (MVP + Stubs)

- Ledger: Accounts, Transactions, JournalEntries, Reports (P&L, Balance Sheet)
- Data Providers:
  - FX (`ECB`, `OpenExchangeRates` # TODO key)
  - Markets (`yfinance` for equities/ETFs; # TODO commodities + futures providers)
  - Macro (# TODO FRED/WorldBank/OECD)
- Tax:
  - Core tax schema + rule engine
  - OECD VAT scaffold (# TODO data puller)
  - US Federal/State stubs (# TODO actual tables + updates)
- Forecasting:
  - ARIMA baseline
  - Event signals placeholder (# TODO NLP + causal features)
- CLI:
  - Import CSV
  - Sync FX and Market prices
  - Generate reports

## Roadmap

- [ ] Rich plugin discovery via entry points
- [ ] Multi-tenant bookkeeping
- [ ] Advanced reconciliation (bank feeds, Plaid # TODO)
- [ ] Caching layer + job queue
- [ ] Fine-grained permissions and audit trail
- [ ] Web UI (React) option (# TODO) alongside Streamlit

See more in `docs/ARCHITECTURE.md` and `docs/PLUGINS.md`.
