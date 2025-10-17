# Repository Assessment

## Structure & Dependency Map
- **apps/api**: FastAPI backend with configuration (`config.py`), database helpers (`db.py`), SQLModel models, routers, services, security, and a background scheduler. Depends on `sqlmodel`, `fastapi`, and plugin modules.
- **apps/web**: Streamlit front end orchestrating reports and workflows through the API.
- **cli**: Click-based management commands for bootstrapping data and invoking services.
- **plugins**: Provider implementations (FX, market data, tax) dynamically loaded via configuration.
- **docs/tests**: Extensive documentation and pytest suite covering API endpoints, services, and integrations.
- **docker**: Container orchestration assets for local deployment.

## Key Findings
1. **Deprecated lifecycle hooks**: `apps/api/main.py` still relies on `@app.on_event` startup/shutdown handlers, triggering FastAPI deprecation warnings and risking future breakage as the framework shifts to lifespan protocols.
2. **Silent scheduler failures**: `apps/api/scheduler.py` swallows all exceptions when refreshing forecasts, giving no visibility into failures and leaving stale data undetected.
3. **Weak secret defaults**: Configuration defaults to `JWT_SECRET_KEY="change-me"`; without overrides deployments are insecure. No runtime guard warns operators.
4. **Scheduler coupling**: Background job instantiates services directly against the global engine without dependency inversion, complicating testing and observability.

## Risk Notes
- Transition away from deprecated lifecycle hooks is urgent to avoid sudden breakage on FastAPI upgrades.
- Silent failures in the APScheduler job mean forecast data could be stale without operators noticing.
- Default JWT secret invites accidental insecure deployments if environment variables are missed.
- Background scheduler shares global state; concurrent access needs careful session management (currently mitigated by SQLModel's session scoping but worth monitoring).

## Test Posture
- `pytest` suite covers API routes, services, CLI, plugin loader, and smoke paths; 40 tests currently pass but emit deprecation warnings tied to the FastAPI lifecycle API.
- No direct coverage ensures scheduler error handling or logging semantics.

## CI/CD Posture
- No CI configuration present; all quality gates rely on local execution. No automated linting or formatting enforcement defined.

## Modes Selected
- **Zero-Bloat Refactor**: Resolve deprecated FastAPI lifecycle usage and tighten scheduler implementation without changing outward behavior.
- **Test & Verify**: Add regression coverage for scheduler behavior, especially around error handling/logging to guard against silent failures.

## Verification
- `pytest -q` (passes with existing third-party deprecation warnings from passlib/Streamlit)
