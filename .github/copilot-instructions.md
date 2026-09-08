# Copilot instructions for Modular Accounting

Read root `AGENTS.md` and any applicable scoped instructions before changing the repository. Preserve pre-existing checkouts, worktrees, local databases, environment files, and user data.

## Application boundaries

- Backend: FastAPI in `src/apps/api`, imported as `apps.api`; SQLModel with SQLite by default.
- UI: Streamlit in `src/apps/web/app.py`; `apps/web/app.py` is the compatibility launcher.
- Providers: explicitly configured modules under `src/plugins/`, imported as `plugins.*`.
- Authoritative standalone SDK: `packages/provider-sdk/src/modular_accounting_provider_sdk`; `apps.provider_sdk` is an identity-preserving compatibility facade, not a second implementation.
- This is a public Early Beta / Portfolio Preview, not a production accounting or provider-certification service.

## Changes and trust

- Keep public API contracts stable and changes focused on the active slice.
- Use `src/apps/api/config.py` and its `Settings.load(...)` / `get_settings` patterns for configuration.
- `settings.allowed_providers` is the sole executable provider trust source. Packaging, importability, manifests, entry points, and persisted governance state cannot authorize code execution.
- Use the provider loader in `src/apps/api/services/plugin_loader.py`, not tenant-supplied module imports. Tenant governance may only narrow process trust; authorize membership before discovery or provider resolution.
- Register API routers in the application factory in `src/apps/api/main.py` and use the existing session and audit dependencies.
- Keep evidence export content and its header bound to the same `service.evidence()` result. Never independently recompute them.
- Required tests must remain hermetic; do not make live financial-provider requests a prerequisite for passing tests.

## Setup and execution

Install development dependencies with `python -m pip install -r requirements-dev.txt` in the approved environment; do not modify shared environments incidentally.

Expose both source roots before direct module commands:

- PowerShell: `$env:PYTHONPATH = "$PWD\src;$PWD\packages\provider-sdk\src"`
- bash/zsh: `export PYTHONPATH="$PWD/src:$PWD/packages/provider-sdk/src${PYTHONPATH:+:$PYTHONPATH}"`

Run from the verified repository worktree:

- API: `python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000`
- UI: `python -m streamlit run apps/web/app.py --server.address 127.0.0.1`; configure `API_BASE` for the loopback API.
- Focused regression: `python -m pytest -q tests/test_provider_governance_api.py`
- Full gate: `python -m src.tools.quality_gate` or `make quality-gate`.

## Secrets and validation

- There is no fixed `change-me` JWT default. Without a configured secret, `_resolve_jwt_secret` generates an ephemeral value and tokens rotate on restart.
- Configure `MODACCT_JWT_SECRET_KEY` or the supported `JWT_SECRET_KEY` fallback when persistence is needed. Compose requires an explicit secret; never print or commit its value.
- Use existing test fixtures for isolated configuration and databases; do not invent production credentials.
- Preserve aggregate line coverage, independent critical-module line/branch floors, changed-production coverage, accounting controls, dependency audits, and secret scanning.
- Keep existing workflows and required checks intact. A source-file edit cannot change live GitHub ruleset enforcement.
- Record actual validation, exact source SHA, and any blocked checks without claiming an unexecuted pass. Merging or publishing still requires separate owner authorization.
