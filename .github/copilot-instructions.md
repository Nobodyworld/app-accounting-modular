<!--
Guidance for AI coding agents working on the Modular Accounting repo.
Keep this file concise (~20-50 lines). Update only with project-discoverable facts.
-->

# Copilot instructions for Modular Accounting

Be pragmatic and project-aware. This repository is a small, modular accounting platform:

- Backend: FastAPI app in `src/apps/api` (imported as `apps.api`; SQLModel + SQLite by default).
- UI: Streamlit app in `src/apps/web/app.py` that talks to the API via `API_BASE`.
- Plugins: Drop-in provider modules under `src/plugins/` (imported as `plugins.*`, e.g. `plugins.fx_ecb.provider`).

What to change and how

- Prefer minimal, local changes. Keep public APIs stable (routers under `src/apps/api/routers`).
- Use existing config patterns in `src/apps/api/config.py` (Settings.load/get_settings) when adding environment-driven options.
- Plugin discovery uses `src/apps/api/services/plugin_loader.py`: add provider modules under `src/plugins/` and register them via `DEFAULT_ALLOWED_PROVIDERS` in `config.py`.

Key files and examples (copy or reference these patterns):

- App factory: `src/apps/api/main.py` — call `init_db()` and include routers via `app.include_router(...)`.
- DB: `src/apps/api/db.py` — uses SQLModel, `get_session()` yields sessions for FastAPI dependencies.
- Plugin: `src/plugins/fx_ecb/provider.py` — expose a `provider()` factory returning an object with required methods (e.g. `sync_daily_rates`).
- Streamlit UI: `src/apps/web/app.py` — calls API endpoints and demonstrates parameter usage.

Run, test, and dev commands

- Install dependencies: `pip install -r requirements.txt`.
- Expose src-layout packages before direct module commands: PowerShell `$env:PYTHONPATH = "$PWD\src"`; bash/zsh `export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"`.
- Run API locally: `python -m uvicorn apps.api.main:app --reload` (the tests and Streamlit expect API on http://localhost:8000).
- Run UI: `streamlit run src/apps/web/app.py` (sets `API_BASE` to point at the running API if not set).
- Run all tests: use the test runner in this repo (pytest is implied). Tests expect an in-repo importable path; see `tests/conftest.py`.

Project-specific conventions

- Config: Use `src/apps/api/config.py` and `Settings.load(...)` to respect `MODACCT_` prefixed env vars.
- DB: SQLite is default. For in-memory tests, `db.engine` uses StaticPool to share connections. Avoid recreating engines.
- Providers: keys use the pattern `{capability}:{provider}` (e.g. `fx:ecb`, `market:yfinance`). Use matching `module` strings in `DEFAULT_ALLOWED_PROVIDERS`.
- Secrets: JWT secret default is `change-me` in settings; tests rely on the default unless env overrides are provided.

Patterns and anti-patterns to follow

- Prefer the plugin loader (`load_provider`) over direct imports of `plugins.*` modules.
- When adding API routes, register them under `src/apps/api/routers/` and include in the factory in `src/apps/api/main.py`.
- Tests emulate missing third-party modules by stubbing (see `tests/conftest.py` multipart stub). Mirror that technique when writing tests that require optional deps.

Examples you can use in generated code

- Load a provider safely:
  from apps.api.services.plugin_loader import load_provider
  handle = load_provider('fx:ecb')
  for rate in handle.instance.sync_daily_rates(base='EUR'):
  pass

Verify and lint

- Run focused pytest suites after edits. Use `make quality-gate` or `python -m src.tools.quality_gate` for the full Ruff, format, mypy, pytest, dependency-audit, and current-tree secret-scan gate.

If anything is unclear

- Reference `README.md` and `docs/` for higher-level goals.
- Ask for missing runtime details (e.g., Docker secrets, external API keys) — do not invent credentials.

Thanks — after making changes, run the test suite and update this file only if new discoverable conventions are introduced.
