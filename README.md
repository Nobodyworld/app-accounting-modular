# Modular Accounting

[![CI](https://github.com/modular-accounting/modular-accounting/actions/workflows/ci.yml/badge.svg)](https://github.com/modular-accounting/modular-accounting/actions/workflows/ci.yml)
[![CodeQL](https://github.com/modular-accounting/modular-accounting/actions/workflows/codeql.yml/badge.svg)](https://github.com/modular-accounting/modular-accounting/actions/workflows/codeql.yml)

Modular Accounting ("ModAcct") is a composable finance platform that blends a FastAPI backend, a Streamlit operator console, and a plugin-driven integration layer. Teams can stand up ledgering, reporting, FX, market-data, tax, and forecasting workflows without committing to a monolithic vendor stack.

## Table of Contents
- [Key Capabilities](#key-capabilities)
- [Quick Start](#quick-start)
- [Usage Examples](#usage-examples)
- [Architecture Overview](#architecture-overview)
- [Service and API Map](#service-and-api-map)
- [Configuration](#configuration)
- [Developer Workflow](#developer-workflow)
- [Testing](#testing)
- [Project Structure](#project-structure)
- [Community & Support](#community--support)

## Key Capabilities
- **Ledger & Reporting** – SQLModel-backed double-entry primitives, cashflow and budget variance APIs, and Streamlit dashboards for finance teams.
- **Forecasting** – Forecast and budgeting services with ARIMA baselines and hooks for exogenous signals (events, FX volatility, macro inputs).
- **Integrations** – Pluggable provider contracts for FX, market pricing, and jurisdiction-specific tax rules with first-party examples under `plugins/`.
- **Observability** – Structured logging with correlation IDs across API, scheduler, and CLI plus audit trails on authentication events.
- **Portability** – Ships with SQLite for zero-setup dev environments but can target any SQLAlchemy-compatible database.

## Quick Start
```bash
# Clone & bootstrap
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env

# Launch API (http://localhost:8000/docs)
uvicorn apps.api.main:app --reload

# Launch Streamlit console (http://localhost:8501)
streamlit run apps/web/app.py
```

Docker users can run the entire stack (API + Streamlit + background workers) using:

```bash
docker-compose up --build
```

## Usage Examples
### Authenticate & Post a Transaction
```bash
# Obtain an access token
curl -X POST http://localhost:8000/auth/token \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'username=demo@example.com&password=demo-password'

# Use the token to create a journal entry
curl -X POST http://localhost:8000/ledger/transactions \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{
        "organization_id": 1,
        "description": "Invoice payment",
        "postings": [
          {"account_id": 100, "amount": "-1250.00", "currency": "USD"},
          {"account_id": 200, "amount": "1250.00", "currency": "USD"}
        ]
      }'
```

### Sync FX Rates from the CLI
```bash
python -m cli.macli sync-fx --base EUR --provider ecb_reference_via_exchangerate_host
```

### Explore Dashboards
Launch the Streamlit console and navigate to **Reports → Cashflow Forecast** to visualise ledger balances, FX overlays, and forecast diagnostics.

### Add a Custom Provider
1. Create a folder under `plugins/your_provider` with a `provider.py` exporting `provider()`.
2. Implement the required protocol (see [docs/PLUGINS.md](docs/PLUGINS.md)).
3. Configure the provider key in `.env` or the database.
4. Verify the provider appears in `GET /core/providers`.

## Architecture Overview
```
┌────────────────────────────┐      ┌───────────────────────┐
│ Streamlit Operations UI    │◀────▶│ FastAPI REST Backend  │◀─┐
│ (apps/web)                 │      │ (apps/api)            │  │
└──────────────┬─────────────┘      └───────────┬───────────┘  │
               │                                │              │
               │                                ▼              │
               │                     Services (ledger, fx,     │
               │                     market, tax, forecast,    │
               │                     workflow)                 │
               │                                │              │
               ▼                                ▼              │
        CLI Utilities                    SQLModel Persistence   │
        (cli/macli.py)                   (SQLite/Postgres)      │
               │                                │              │
               └──────────────┬─────────────────┴──────────────┘
                              ▼
                       Plugin Ecosystem
                       (plugins/*)
```

- **Scheduler** – `apps/api/scheduler.py` orchestrates recurring jobs (e.g., FX/market refresh). Startup and shutdown hooks integrate with the FastAPI lifespan manager.
- **Observability** – `apps/observability/logging.py` configures JSON/text logging, correlation IDs, and request middleware shared across entry points.
- **Audit Trail** – Authentication flows record structured entries via `apps/api/audit.py`.

## Service and API Map
| Area | Module | Representative Endpoints |
| --- | --- | --- |
| Core | `apps/api/routers/core.py` | `GET /core/health`, `GET /core/providers` |
| Auth & Security | `apps/api/routers/auth.py`, `apps/api/security.py` | `POST /auth/token`, `GET /auth/me` |
| Ledger | `apps/api/services/ledger_service.py`, `apps/api/routers/ledger.py` | `POST /ledger/transactions`, `GET /ledger/accounts` |
| FX | `apps/api/services/fx_service.py`, `apps/api/routers/fx.py` | `POST /fx/sync`, `GET /fx/rates` |
| Market Data | `apps/api/services/market_service.py`, `apps/api/routers/market.py` | `POST /market/prices`, `GET /market/instruments` |
| Tax | `apps/api/services/tax_service.py`, `apps/api/routers/tax.py` | `POST /tax/rules/sync`, `GET /tax/rules` |
| Forecasting & Reports | `apps/api/services/forecast_service.py`, `apps/api/routers/forecast.py`, `apps/api/routers/reports.py` | `POST /forecast/series`, `GET /reports/budget-vs-actual` |
| Workflow | `apps/api/services/workflow_service.py`, `apps/api/routers/workflow.py` | `POST /workflow/run`, `GET /workflow/status` |

Full schema documentation lives at `/docs` (Swagger UI) and `/redoc` once the API is running.

## Configuration
- Settings are centralised in `apps/api/config.py` using Pydantic settings. They honour `MODACCT_`-prefixed environment variables with `.env` support.
- Review [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for variable reference tables, dotenv handling, and security notes.

## Developer Workflow
- Install tooling and hooks via `pre-commit install --install-hooks --hook-type commit-msg`.
- Run formatters and linters locally:
  ```bash
  pre-commit run --all-files
  ```
- Execute the application test suite:
  ```bash
  pytest
  ```
- Type checking (gradually stricter coverage) leverages mypy; see [PLAN.md](PLAN.md) for rollout milestones.

## Testing
The pytest suite covers routers, services, the scheduler, observability utilities, and CLI entry points. Streamlit smoke tests ensure dashboards mount successfully. CI executes `pytest` and code quality checks on every push.

## Project Structure
```
apps/
  api/        FastAPI application, routers, services, scheduler
  web/        Streamlit dashboards
cli/          Click-based CLI entry point
plugins/      Provider contracts and implementations
docs/         Architecture and domain documentation
tests/        Pytest suite
```

## Community & Support
- Contribution guidelines: [CONTRIBUTING.md](CONTRIBUTING.md)
- Code of Conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- Security disclosures: [SECURITY.md](SECURITY.md)
- Support channels and SLAs: [SUPPORT.md](SUPPORT.md)
