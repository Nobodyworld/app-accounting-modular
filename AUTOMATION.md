# Automation & Agent Playbook

This document explains how human and AI agents should interact with the
repository to remain safe, observable, and reversible.

## Golden rules

1. **Use the Makefile targets**. `make quality` executes linting, type checks,
   and tests with coverage gates. `make health` runs a full suite of health
   probes using the CLI.
2. **Record decisions in docs**. Significant architectural or operational
   changes should be summarised in `ARCHITECTURE_OVERVIEW.md` and the relevant
   README section.
3. **Tag TODOs** with the `[priority][estimate]` format (for example
   `# TODO[P2][2d]: Add async provider loading`). This keeps the future work
   queue machine-readable.
4. **Avoid direct writes to production databases**. Integration tests spin up
   SQLite automatically; any external database access must go through the
   configured SQLModel engine.

## Operational checklist for agents

1. Install dependencies (`make install`).
2. Run targeted quality gates during development:
   * `make lint` – style and bugbear checks.
   * `make typecheck` – strict mypy coverage across application, API, and
     extension layers.
   * `make test` – pytest with coverage ≥ 85%.
3. Validate runtime health before handoff:
   * `make health` – executes `macli health` to confirm database connectivity,
     scheduler state, metrics export, and extension probes.
   * `curl http://localhost:8000/health/ready` – verifies HTTP readiness when
     the API is running.
4. Generate release collateral:
   * Update `CHANGELOG.md` and `RELEASE_NOTES.md`.
   * Attach coverage summaries to `REPORTS/` when appropriate.

## Safety valves

* **Extension isolation** – register new capabilities through the extension
  registry (`apps/extensions/registry.py`) to avoid modifying core modules.
* **Observability** – when building automation, emit metrics using
  `apps.observability.metrics.snapshot_telemetry` or register custom gauges and
  counters.
* **Health reporting** – any long-running automation should register a health
  probe via `register_health_check` so its status appears in `/health/ready`.

## Incident response

1. Use `macli health` to capture an immediate snapshot of subsystem status.
2. Inspect logs with correlation IDs (CLI and HTTP both emit `correlation_id`
   fields) to trace requests end-to-end.
3. Roll back recent deployments by reverting the Git commit or disabling the
   affected extension in configuration (`MODACCT_ALLOWED_EXTENSIONS__key__enabled=false`).

Following this playbook ensures agents keep the platform observable, recoverable,
and ready for future automation.
