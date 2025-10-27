# Diagnostic Report

## Code Health Overview
- **Database Bootstrap** (`apps/api/db.py`): still uses `SQLModel.metadata.create_all` at runtime; Alembic migrations remain a TODO for production hardening.
- **Scheduler Lifecycle** (`apps/api/scheduler.py` & `apps/api/main.py`): lifecycle guards prevent duplicate job registration, but resilience improvements (retry/backoff) are still open.
- **Security Gaps** (`apps/api/security.py` & routers): refresh tokens, MFA, and rate limiting are outstanding TODOs though audit logging is in place.
- **Router Validation**: pagination and scoping placeholders remain in several routers (`reports`, `workflow`, `market`), risking large responses.
- **Plugin Loader**: interface validation and richer metadata caching are noted TODOs to avoid runtime surprises.

## Typing & Style Issues
- Strict mypy coverage now spans config, audit, security, and metadata utilities; remaining services and routers require additional annotations.
- Plugin packages lacked docstrings/exports but have now been standardised to aid discovery and typing.

## Testing & CI
- Pytest suite exercises core paths; CI (GitHub Actions) runs linting, tests, and CodeQL scanning.
- Scheduler/background workflows have smoke coverage but could benefit from resilience-focused integration tests.

## Documentation State
- README and `docs/` have been expanded with end-to-end usage examples, reducing earlier drift between code and docs.
- CONTRIBUTING now codifies documentation expectations; future changes should treat doc updates as part of the Definition of Done.

## TODO / FIXME Classification
- **Critical:**
  - Implement rate limiting and refresh tokens in the authentication flow.
  - Enforce organisation scoping and pagination across reports/workflow routers.
  - Introduce migration tooling to replace runtime `create_all` calls.
- **Moderate:**
  - Enhance plugin loader validation, cache invalidation, and health checks.
  - Expand type coverage for remaining services.
  - Add scheduler resilience (retry/backoff, metrics integration).
- **Minor:**
  - Continue fleshing out forecasting strategies, audit pagination, and observability metrics.

## Recommended Modes
- **Architecture Alignment** – clarify boundaries around scheduler resiliency and plugin lifecycle.
- **Zero-Bloat Refactor** – remove remaining duplication in services/routers as type coverage increases.
- **Full-System Polish** – continue enforcing documentation and linting standards repo-wide.
- **Test & Verify** – build targeted integration tests for background jobs and plugin failure modes.
- **Security & Stability Audit** – prioritise authentication hardening and migration tooling.
