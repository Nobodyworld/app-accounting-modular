# Automation & Agent Playbook

This document explains how human and AI agents should interact with the
repository to remain safe, observable, and reversible.

## Golden rules

1. **Use the Makefile targets**. `make quality` executes linting, type checks,
   tests with coverage gates, and security scanning. `make ci` mirrors the full
   pipeline for local smoke checks. `make health` runs a full suite of health
   probes using the CLI, and `make audit` snapshots coverage/complexity metrics
   via the trace-based fallback for air-gapped environments. When coverage data
   already exists, rerun `tools.audit_metrics` with `--skip-trace` to reuse the
   stored `.cover` files and refresh only the lightweight metrics.
   Pair `make health` with `python -m cli.macli inspect-extensions` to verify
   extension manifests loaded and expose version metadata for release notes.
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
   * `python -m cli.macli inspect-extensions` – captures manifest metadata and
     load status for each configured extension.
   * `python -m cli.macli inspect-contracts` – lists automation contracts
     published by extensions so orchestrators know which hooks are available.
   * `curl http://localhost:8000/health/ready` – verifies HTTP readiness when
     the API is running.
   * `curl http://localhost:8000/health/telemetry` – aggregates metrics,
      extension status, and health probes for dashboards or runbooks.
4. Generate release collateral:
   * Update `CHANGELOG.md` and `RELEASE_NOTES.md` (or run
     `make release PART=patch MESSAGE="<summary>"` to bump the version and
     seed both files automatically).
   * Run `make audit` to refresh `REPORTS/audit-latest.md` with up-to-date
     metrics whenever steward reports are compiled. If trace collection is too
     slow, rerun `tools.audit_metrics --skip-trace` to reuse the prior coverage
     snapshot while still emitting complexity and dependency profiles.

## Safety valves

* **Extension isolation** – register new capabilities through the extension
  registry (`apps/extensions/registry.py`) to avoid modifying core modules.
* **Observability** – when building automation, emit metrics using
  `apps.observability.metrics.snapshot_telemetry`, register custom gauges and
  counters, and wrap long-running blocks with `apps.observability.tracing.traced`
  so trace IDs propagate through structured logs.
* **Health reporting** – any long-running automation should register a health
  probe via `register_health_check` so its status appears in `/health/ready`.

## Incident response

1. Use `macli health` to capture an immediate snapshot of subsystem status.
2. Inspect extension load telemetry via `macli inspect-extensions` (table or
   JSON) to confirm the modules your automation depends on are available.
3. Inspect logs with correlation IDs (CLI and HTTP both emit `correlation_id`
   fields) to trace requests end-to-end.
4. Roll back recent deployments by reverting the Git commit or disabling the
   affected extension in configuration (`MODACCT_ALLOWED_EXTENSIONS__key__enabled=false`).
5. Regenerate extension packages with `macli scaffold-extension` when
   backfilling automation or agent-specific hooks to ensure the latest tracing
   primitives are included.

Following this playbook ensures agents keep the platform observable, recoverable,
and ready for future automation.
