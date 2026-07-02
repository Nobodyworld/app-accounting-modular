# Repository Context Report

## Stack Overview

- **Primary language:** Python 3.12+ with Python 3.14 as the primary development
 baseline.
- **Frameworks and libraries:** FastAPI, SQLModel, Pydantic v2, APScheduler,
 Streamlit, pandas/numpy, statsmodels, scikit-learn, and Click-based CLI
 orchestration.
- **Testing tooling:** Pytest suites under `tests/` cover services, routers,
 CLI commands, scheduler behavior, Streamlit smoke checks, and accounting
 controls.
- **Formatting and linting:** Ruff and Ruff format use a 120-character line
 length; mypy covers the most critical API, accounting, extension, and CLI
 modules.

## Dependency & Build Tooling

- **Dependency management:** `requirements.txt` and `requirements-dev.txt` define
 bounded runtime and development dependencies.
- **Containerization:** Docker assets live under `config/`.
- **Configuration:** Runtime settings live in `src/apps/api/config.py`, with
 `.env` examples under `config/.env.example`.

## Project Structure

- `src/apps/` - Python service packages for API, accounting, extensions,
 observability, and web.
- `src/cli/` - Demo and operational CLIs for snapshots, health, observability,
 and extension inspection.
- `src/plugins/` - Reference provider adapters and operational extensions.
- `apps/` - Frontend placeholders retained outside the Python runtime source.
- `docs/` - Architecture, governance, operations, release, and example guides.
- `tests/` - Pytest suites mirroring the runtime modules.

## CI/CD & Operations

- GitHub Actions workflows are configured for quality gates and CodeQL scanning.
 Hosted execution evidence for the current publication commit is not recorded
 in the public release audit.
- Renovate configuration automates dependency update proposals.
- Structured logging, health probes, metrics, and tracing helpers live under
 `src/apps/observability/`.

## Documentation Health

- `README.md` and `docs/` describe the modular accounting toolkit scope, path
 layout, adapter contracts, CLI workflows, and foreign-currency case study.
- Public release status is tracked in `PUBLIC_RELEASE_AUDIT.md`; use that file
 as the source of truth for current classification and blockers.

## Next Steps

Complete the public-release blockers: run a full-history secret scan, clean-clone
validate the final publication commit, record hosted CI disposition, and add
first-screen visual evidence for employer review.
