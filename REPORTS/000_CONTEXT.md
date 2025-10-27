# Repository Context Report

## Stack Overview
- **Primary Language:** Python 3.11 with FastAPI backend and Streamlit frontend.
- **Frameworks & Libraries:** FastAPI, SQLModel, Pydantic v2, APScheduler, Streamlit, pandas/numpy, statsmodels for forecasting, Click for CLI orchestration.
- **Testing Tooling:** Pytest-based suite under `tests/` covering services, routers, CLI commands, scheduler behaviour, and Streamlit smoke checks.
- **Formatting & Linting:** Black (line length 88) and Ruff with import sorting; Markdown/YAML handled by Prettier via pre-commit.

## Dependency & Build Tooling
- **Dependency Management:** `requirements.txt` / `requirements-dev.txt` pinned for reproducibility.
- **Containerisation:** `docker-compose.yml` plus `docker/` assets for API, scheduler, database, and web console.
- **Configuration:** Centralised `apps/api/config.py` using Pydantic settings with `.env` support; documented comprehensively in `docs/CONFIGURATION.md`.

## Project Structure
- `apps/api` – FastAPI application (config, routers, services, scheduler, security, observability helpers).
- `apps/web` – Streamlit UI composing charts and operational dashboards.
- `cli` – Click-based administrative commands for data ingestion and sync workflows.
- `plugins` – Provider implementations for FX, market data, and tax (dynamically imported by the plugin loader).
- `docs` – Expanded documentation suite (architecture, forecasting, plugins, AI interface, tax model, configuration).
- `tests` – Pytest suite with fixtures for SQLModel sessions and provider stubs.

## CI/CD & Operations
- GitHub Actions workflows run linting, formatting, tests, and CodeQL scans. Badges are published in `README.md`.
- Renovate configuration automates dependency updates.
- Structured logging funnels through `apps/observability/logging.py`, with correlation IDs exposed across API, scheduler, and CLI contexts.

## Documentation Health
- `README.md` and `docs/` now include usage examples, architecture diagrams, and provider development guidance to support rapid onboarding.
- Governance and support files (`CODE_OF_CONDUCT.md`, `SECURITY.md`, `SUPPORT.md`) align with contribution expectations defined in `CONTRIBUTING.md`.

## Next Steps
Continue executing the modernisation plan outlined in `PLAN.md`: broaden strict typing coverage, introduce metrics/telemetry, and build on the refreshed documentation to streamline contributor onboarding.
