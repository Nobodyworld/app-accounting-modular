# Architecture Overview

Modular Accounting now exposes a layered architecture with shared observability
and extension scaffolding so that new modules can be introduced without
touching the core. The diagram below illustrates the major runtime surfaces.

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                             Entry Points                                 │
│  - FastAPI (src/apps/api/main.py)                                        │
│  - CLI (src/cli/macli.py)                                                │
│  - Scheduled jobs (src/apps/api/scheduler.py)                            │
└───────────────┬───────────────────────────────┬──────────────────────────┘
                │                               │
┌───────────────▼───────────────┐   ┌───────────▼────────────────────────┐
│ Application Services           │   │ Observability Layer                 │
│ - DataSnapshotService          │   │ - Structured logging                │
│   (src/apps/modular_accounting/│   │   (src/apps/observability/logging.py)│
│    application/snapshots.py)   │   │ - Metrics + health registry         │
│ - Telemetry adapter            │   │   (apps/observability/{metrics,     │
│   (src/apps/modular_accounting/│   │    health}.py)                      │
│    application/telemetry.py)   │   │ - ExtensionTelemetryAdapter         │
│ - Tracing context helpers      │   │   (src/apps/observability/metrics.py)│
│   (src/apps/observability/tracing.py)│ │ - Diagnostics snapshot              │
│                                │   │   (src/apps/observability/diagnostics.py)│
│                                │   │ - Tracing + trace middleware        │
└───────────────┬───────────────┘   │   (src/apps/observability/tracing.py)│
                │                   └───────────┬────────────────────────┘
                │                                │
┌───────────────▼───────────────┐   ┌───────────▼────────────────────────┐
│ Domain Ports & Providers       │   │ Extension Registry                 │
│ - Ports (src/apps/modular_     │   │ - src/apps/extensions/registry.py  │
│   accounting/domain/ports.py)  │   │ - Default extension loader         │
│ - Provider loader (src/apps/api/│   │   (src/apps/api/services/          │
│   services/plugin_loader.py)   │   │    extension_loader.py)             │
│ - Built-in plugins (src/plugins/)│   │ - Baseline analytics extension     │
└───────────────────────────────┘   │   (src/plugins/analytics_baseline/)  │
                                     │ - Operations heartbeat extension    │
                                     │   (src/plugins/ops_heartbeat/)      │
                                     └────────────────────────────────────┘
```

## Runtime flow

1. **Entry points** initialise logging, tracing, metrics middleware, and
   database state.  The FastAPI app wires both `RequestTraceMiddleware` and
   `RequestMetricsMiddleware` so every request gains a traceparent header and
   latency metrics, while the CLI uses `logging_context` + `traced` to provide
   correlation IDs and trace IDs for background work.  A dedicated
   `StartupManager` (`src/apps/api/startup.py`) now orchestrates the API bootstrap
   sequence so logging/tracing configuration, database initialisation, health
   registration, and extension loading emit structured step metadata.  The
   collected records are exposed via `app.state.startup_records` for diagnostics
   and surfaced in logs for incident response, while fatal failures emit an
   aggregated "startup sequence aborted" summary before bubbling the error so
   operators can see which steps executed or failed.
   `RequestBodyLimitMiddleware` performs a bounded ASGI receive before route
   execution. It is wrapped by tracing, request context, and metrics so
   sanitized `413` rejections remain observable without retaining or logging
   rejected content.
   Authentication routes delegate persisted session creation, access
   enforcement, refresh compare-and-swap rotation, revocation, and expiration
   cleanup to `src/apps/api/services/auth_session_service.py`. Streamlit retains
   the returned token pair only in memory and performs at most one refresh and
   one retry for a protected request.
2. **Extension loader** imports every enabled module declared in
   `Settings.allowed_extensions`. Extensions register an `ExtensionManifest`
   with `src.apps.extensions.registry.extension_registry` and can contribute health
   checks or custom instrumentation. The loader now emits metrics via
   `ExtensionTelemetryAdapter` so dashboards can monitor load durations and
   gauge whether a module is both enabled and successfully initialised.
3. **Application services** orchestrate domain operations. For example,
   `DataSnapshotService` normalises `SnapshotRequest` payloads, resolves data
   through ports, and records cache utilisation and latency metrics via the
   telemetry adapter. `ScenarioPlan` and `ScenarioPlanSummary` promote plan
   parsing to the application layer so CLI commands and HTTP endpoints reuse
   the same validation, metadata handling, and coverage analysis. Combined with
   `ScenarioSnapshotRunner`, the snapshot service can execute multiple
   `SnapshotScenario` definitions, aggregate diagnostics, and expose the batch
   to both the CLI and HTTP endpoint without duplicating orchestration logic.
   Scenario executions emit dedicated metrics
   (`modacct_scenario_runs_total`, `modacct_scenario_latency_seconds`, and
   `modacct_scenario_inflight`) so dashboards can correlate orchestration load
   with cache performance. The telemetry adapter now includes an asynchronous
   context manager so long-running `asyncio` workloads inherit the same
   instrumentation guarantees as synchronous batches. `compute_snapshot_diagnostics`
   converts the immutable snapshot into freshness and coverage metrics so every
   surface can surface a consistent health summary without reimplementing the
   analysis.
4. **Domain ports and providers** continue to act as the integration boundary
   for external data. Providers are loaded via the existing plugin loader and
   the new extension registry complements rather than replaces this system.
   The ECB and OpenExchangeRates adapters share a bounded HTTPS JSON transport:
   streamed reads, declared and measured 1 MiB byte enforcement, 5/20-second
   connect/read timeouts, two selected-transient attempts, sanitized domain
   errors, and a 512-rate cap. YFinance makes one non-threaded high-level call
   with a 20-second timeout and 10,000-day/row limits. Because that dependency
   materializes its DataFrame internally, its HTTP response cannot be
   independently streamed or byte-counted at this adapter layer. Demo/reference
   providers perform no external I/O.

## Accountant close domain

The v0.2 close tranche follows the existing service-first architecture rather than placing accounting decisions in FastAPI or Streamlit:

- `close_service.py` owns lifecycle guards, typed administrator-only policy overrides, atomic version/content-revision compare-and-swap updates, required control scope, revision-aware readiness, effective checklist status, and finalization.
- `period_lock.py` acquires a SQLite tenant writer gate before period overlap decisions and before either close or direct/workflow posting evaluates period state. An accepted in-period post advances the period's authoritative ledger-activity revision in the same transaction. `auto_process=true` stages and posts in one request transaction.
- `reconciliation_service.py` derives account balances, binds reconciliations and durable period-scoped variance runs to ledger activity, creates fresh rows owned by every variance rerun, and owns one current approval per durable journal reference plus append-only decisions.
- `close_evidence_service.py` builds cycle-scoped, row-bounded deterministic ZIP bytes, including current variance rows and durable run/approval history, and conditionally persists safe manifest metadata against cycle status, close revision, and ledger revision.
- `routers/close.py` performs persisted-session authentication, tenant/role authorization, response-schema translation, and deliberate `400`/`403`/`404`/`409` mapping.
- `close_workspace.py` uses the existing one-refresh Streamlit API session and renders the API's readiness result rather than recalculating accounting controls.

`AccountingPeriod.status` and `ledger_activity_revision` are authoritative. The lifecycle is `DRAFT → IN_PROGRESS/BLOCKED → READY_FOR_APPROVAL → CLOSED`. Ready freezes operational rows and all in-period posting and can return to work only with an administrator reason. Subsequent posting advances the ledger revision and makes older reconciliation, variance, and evidence proof stale. Cancellation preserves the durable cycle and can restart with a reason. Create and reopen acquire the same overlap gate before querying. Final close recalculates revision-aware readiness, establishes the final content revision, closes cycle and period, and records deterministic `CLOSED` evidence in one transaction. SQLite's single-writer gate is the validated backend strategy; a multi-writer deployment must replace it with database-native row locking or an equivalent posting gate.
5. **Observability** collects metrics, traces, and health reports. Metrics are
   exposed through `/health/metrics` while `/health/telemetry` and
   `apps.observability.diagnostics.collect_observability_snapshot` aggregate the
   current Prometheus exposition, registered health probes, tracing
   configuration, and extension load status into the payload consumed by the new
   `macli observe` command. Health probes cover database connectivity, scheduler
   state, tracing exporter configuration, and extension readiness, and the
   metrics registry now records latency and status for every probe so failing
   checks surface immediately. Extensions can register additional probes without
   touching API code. The tracing module ships a `_noop_exporter` sentinel so
   spans cleanly downgrade to console logging when OpenTelemetry exporters are
   unavailable. `/extensions/contracts`, `macli inspect-contracts`, and the
   reference `src/plugins/ops_resilience` incident-playbook extension expose
   operational contracts to automation tooling.

## Operational safeguards

* Health probes cover database connectivity, scheduler state, metrics export,
  tracing configuration, and extension readiness. CLI tooling mirrors these
  checks via `macli health`, `macli inspect-extensions`, `macli inspect-contracts`,
  and the new `macli observe` snapshot so automation has a consistent view of
  manifests, contracts, and live telemetry.
* The `Makefile` standardises quality gates: linting, type checks, tests with a
  coverage threshold, optional safety scans, the scripted `make quality-gate`
  wrapper around `tools.quality_gate`, and the `audit` target for trace-based
  coverage + complexity metrics.
* Cache observers feed Prometheus-compatible counters and gauges so cache hit
  rates and entry counts can be monitored over time, while
  `ExtensionTelemetryAdapter` tracks load latency and success counts.
* `src/apps/api/limits.py` is the single policy source for inbound body,
  collection, metadata, numeric-control, and Streamlit upload bounds. Deployment
  requirements and exact response contracts are documented in
  `docs/resource-limits.md`.
* Access JWTs are authorized against `AuthSession` persistence rather than
  signature validity alone. Hourly APScheduler cleanup and opportunistic bounded
  cleanup remove only refresh-expired session rows; refresh reuse revokes the
  session family conservatively.
* Container dependency resolution is a separate build-time control plane:
  human-reviewed bounded requirements feed a Docker-isolated, hash-locked `uv`
  compiler; its committed Python 3.14/Linux lock feeds both digest-pinned
  Dockerfiles; and CI emits image archives, inventories, SPDX SBOMs, and
  checksums. The ordinary freshness check is offline and never re-resolves
  PyPI. Pull requests retain evidence without write credentials, while a
  separate trusted-event job may bind provenance and SBOM attestations to the
  exported archives. The complete flow and its limits are documented in
  [`../container-supply-chain.md`](../container-supply-chain.md).

## Extension lifecycle

1. Declare an extension module in configuration (defaults ship with
   `observability:demo`, the operations resilience playbook `ops:resilience`,
   and the disabled `reporting:cashflow` reference).
2. Implement a `register(registry)` function that publishes a manifest and
   registers optional hooks.
3. The loader imports the module on application startup, populating manifests,
   registering optional contracts, and exposing metadata to the CLI (`macli
   inspect-extensions`, `macli inspect-contracts`) and HTTP API.

This design allows new feature packs—report exporters, automation bridges, or
AI agents—to be bolted on by registering extensions instead of modifying core
packages. The `macli scaffold-extension` command now generates a fully wired
package skeleton with tracing hooks and, when requested, a starter
observability contract so contributors can start from a proven baseline.
`macli inspect-extensions` provides an immediate, metrics-backed snapshot of
enabled modules, while `src/plugins/ops_heartbeat` and `src/plugins/ops_resilience`
serve as reference implementations for emitting telemetry and publishing
incident playbooks.

## Future-proofing

* **Containerisation** – The API is stateless and depends only on the database;
  deploy behind a load balancer with per-instance caches disabled when scaling
  horizontally. Health endpoints (`/health/live`, `/health/ready`, and
  `/health/telemetry`) are safe for Kubernetes probes.
* **Multi-tenant support** – Persist extension configuration in a tenant-aware
  store and use the extension loader as the boundary for injecting tenant
  context. The telemetry adapters already label metrics by module path, making
  it straightforward to add tenant labels in the future.
* **Automation hooks** – Extension manifests surface capabilities so automation
  agents can decide which module to invoke, while explicit contracts document
  the callable surfaces available to agents. Coupled with the incident response
  guidelines in `docs/operations/automation_playbook.md`, this enables future agentic tooling to safely
  orchestrate new connectors.
* **Release automation** – `tools.release_manager` underpins `make release`,
  which bumps semantic versions and seeds changelog/release notes to keep
  provenance tight as the platform evolves.
