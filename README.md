# Modular Accounting

[![CI](https://github.com/modular-accounting/modular-accounting/actions/workflows/ci.yml/badge.svg)](https://github.com/modular-accounting/modular-accounting/actions/workflows/ci.yml)
[![CodeQL](https://github.com/modular-accounting/modular-accounting/actions/workflows/codeql.yml/badge.svg)](https://github.com/modular-accounting/modular-accounting/actions/workflows/codeql.yml)

A modular accounting platform composed of a FastAPI backend, Streamlit operations console, and pluggable data providers for FX, market data, tax, budgeting, and forecasting workflows.

## Table of Contents
- [Architecture](#architecture)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [Developer Workflow](#developer-workflow)
- [Testing](#testing)
- [Project Structure](#project-structure)
- [Community & Support](#community--support)

## Architecture
- **API Backend (`apps/api`)**: FastAPI service exposing REST endpoints for auth, ledger, reporting, forecasting, FX, market, tax, audit, and workflow orchestration.
- **Streamlit Web (`apps/web`)**: Analyst-facing dashboards backed by the API.
- **Scheduler (`apps/api/scheduler.py`)**: APScheduler jobs refreshing forecasts and provider data.
- **CLI (`cli/macli.py`)**: Administrative commands for bootstrapping accounts, ingesting data, and generating reports.
- **Plugins (`plugins/`)**: Provider contracts for FX, market, and tax integrations.
- **Docs (`docs/`)**: Architecture, forecasting, plugin, and domain references.

## Getting Started
### Prerequisites
- Python 3.11+
- (Optional) Docker & Docker Compose

### Installation
```bash
git clone https://github.com/modular-accounting/modular-accounting.git
cd modular-accounting
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pre-commit install --install-hooks
pre-commit install --hook-type commit-msg
```

### Running Locally
- **API**:
  ```bash
  uvicorn apps.api.main:app --reload
  ```
- **Streamlit UI**:
  ```bash
  streamlit run apps/web/app.py
  ```
- **Docker Compose**:
  ```bash
  docker-compose up --build
  ```

## Configuration

- Copy [`.env.example`](.env.example) to `.env` (or another path) and populate the values with deployment-specific credentials.
- At runtime the application loads configuration using `Settings.load`, which honours the `MODACCT_`-prefixed environment variables, legacy aliases, and optional dotenv files.
- Refer to [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for the full list of supported keys, validation rules, and loading precedence.

## Developer Workflow
- Lint & format:
  ```bash
  pre-commit run --all-files
  ```
- Run tests:
  ```bash
  pytest
  ```
- Static type checks (targeted strict baseline):
  ```bash
  mypy
  ```
- See [CONTRIBUTING.md](CONTRIBUTING.md) for branching strategy, Conventional Commit guidelines, and review expectations.
- Repository settings and future workstreams are documented in [PLAN.md](PLAN.md) and [REPORT.md](REPORT.md).

## Testing
The repository includes pytest-based unit and integration tests covering:
- API routers, services, and scheduler behaviours.
- CLI command smoke tests.
- Streamlit component smoke coverage.

Run `pytest` locally or rely on GitHub Actions (`ci.yml`) for automated validation. Coverage reporting will be integrated in a future milestone.

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
- Review [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidance.
- Adhere to the [Code of Conduct](CODE_OF_CONDUCT.md).
- For security issues, follow the [Security Policy](SECURITY.md).
- Support channels and SLAs are detailed in [SUPPORT.md](SUPPORT.md).
