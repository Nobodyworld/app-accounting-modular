# Diagnostic Report

## Code Health Overview
- **Database bootstrap** (`apps/api/db.py`): relying on `SQLModel.metadata.create_all` in runtime path. Lacks Alembic migrations and executes in request path for SQLite, risking race conditions.
- **Scheduler lifecycle** (`apps/api/scheduler.py` & `apps/api/main.py`): background scheduler starts on import without guard against duplicate jobs under auto-reload; no retry/backoff for DB outages.
- **Security gaps** (`apps/api/security.py` & routers): Missing login throttling/MFA, refresh tokens, auth audit logging. Token decoding lacks structured error logging.
- **Router parameter validation**: multiple routers TODO pagination and scoping (e.g., `reports`, `workflow`) leaving potential denial-of-service via large responses.
- **Plugin loader**: does not validate plugin interfaces or cache provider metadata; runtime errors possible on invalid plugin entrypoints.
- **Docs drift**: README structure list duplicated docker note; docs outdated vs code.

## Typing & Style Issues
- Several modules missing type aliases/docstrings; services return plain dicts without Pydantic models (e.g., forecast/budget services), impacting clarity.
- No Ruff/Black automation; inconsistent blank lines and import ordering observed in various services.

## Testing & CI
- Pytest suite exists but no automated CI. Scheduler/background interactions mostly untested beyond smoke tests.
- Streamlit smoke test depends on environment variable defaults; potential flakes.

## TODO / FIXME Classification
- **Critical:**
  - Security hardening tasks in `apps/api/security.py` and `routers/auth.py` (audit logging, refresh tokens, MFA/throttling).
  - Report router TODO enforcing org scoping (`apps/api/routers/reports.py`).
  - Scheduler retry/backoff TODOs for database resilience.
- **Moderate:**
  - Pagination and caching TODOs across routers/services to avoid heavy payloads.
  - Database migration TODOs for uniqueness constraints and Alembic adoption.
  - Forecast service enhancements (model strategies, timezone handling).
- **Minor:**
  - Metadata caching improvements, audit pagination, doc improvements, plugin validations.

## Recommended Modes
- **Architecture Alignment:** Needed to clarify module boundaries (config/services/routers) and guard scheduler lifecycle.
- **Zero-Bloat Refactor:** Remove redundant imports, tighten service utilities, ensure routers/services instantiate dependencies efficiently.
- **Full-System Polish:** Enforce Black/Ruff, improve docstrings, refresh README.
- **Test & Verify:** Run pytest suite; ensure scheduler/forecast tests stable.
- **Security & Stability Audit:** Patch immediate security gaps (token error handling, secret configuration warnings) and document TODO ownership.
- **AI-Ready Refactor:** Provide structured API docs/schema (OpenAPI already, but add AI interface doc and ensure deterministic service entrypoints).
