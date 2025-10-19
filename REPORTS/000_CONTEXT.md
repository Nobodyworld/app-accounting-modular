# Repository Context Report

## Stack Overview
- **Primary Language:** Python 3.11 (per `pyproject.toml` Black target) with FastAPI backend and Streamlit frontend.
- **Frameworks & Libraries:** FastAPI, SQLModel, Pydantic v2, APScheduler, Streamlit, pandas/numpy, statsmodels for forecasting.
- **Testing Tooling:** Pytest test suite under `tests/` covering services, routers, CLI, scheduler, and Streamlit smoke checks.
- **Formatting & Linting:** Black (line-length 88), Ruff (E/F rules). No JS/TS tooling detected.

## Dependency & Build Tooling
- **Dependency Management:** `requirements.txt` (pinned versions). No poetry/pnpm; plain pip.
- **Containerization:** `docker-compose.yml` and `docker/` definitions for API, scheduler, db, web.
- **Environment Configuration:** `.env.example`, `apps/api/config.py` loads `pydantic_settings` (env-based settings).

## Project Structure
- `apps/api`: FastAPI application (config, routers, services, models, scheduler, security).
- `apps/web`: Streamlit UI (financial dashboards/reporting).
- `cli`: CLI utilities (Typer likely; confirm later during diagnostics).
- `plugins`: Pluggable providers (FX, market data, tax, etc.).
- `docs`: Existing documentation (`ARCHITECTURE.md`, `PLUGINS.md`, etc.).
- `tests`: Extensive pytest coverage for API/services/CLI.
- `REPORT.md`: Legacy report file.

## CI/CD & Ops Signals
- No GitHub Actions or CI configs present in repo root. Tests expected via manual invocation.
- Docker orchestration implies production deploy via containers.

## Conventions & Patterns
- Python modules use snake_case, Pydantic models for schemas, SQLModel for persistence.
- Services live under `apps/api/services` and consumed by routers; uses dependency injection via `dependencies.py`.
- Logging via Python `logging` module; audit trail module present.

## Next Steps
Proceed to deep diagnostic scanning for code quality, architecture concerns, and TODO/FIXME triage.
