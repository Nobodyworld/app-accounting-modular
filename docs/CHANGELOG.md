# Changelog

## Unreleased

- 2026-07-01: Corrected the Apache-2.0 license text, added `NOTICE`
  attribution, and reframed public-release documentation as `KEEP PRIVATE -
  NEAR READY` pending full-history secret scanning, final clean-clone
  validation, hosted CI disposition, and visual evidence improvements.

- 2026-06-30: Advanced public-readiness hardening by fixing async audit worker
  concurrency initialization, resolving scheduler/security test isolation
  regressions, removing stale XPASS expectations, upgrading dev security
  dependencies, reviewing Apache-2.0 licensing/docs alignment, and closing the
  canonical quality gate on Python 3.14 with 244 passing tests at 86.15%
  coverage.

- 2025-05-24: Validated the post-refactor layout by adding directory-level
  READMEs, refreshing repository navigation docs (README, SPEC, STYLE-GUIDE),
  tightening API model typing/logging utilities, and aligning smoke/metadata
  tests with modern Ruff expectations.
- 2025-11-06: Reorganized the repository structure by grouping documentation under
  `docs/architecture`, `docs/governance`, and `docs/operations`, relocating audit
  artifacts to `docs/reports`, updating automation tooling defaults, and
  annotating TASKLIST entries with explicit review statuses for stewardship
  visibility.
- 2025-11-05: Rebuilt the `macli` CLI to expose health, telemetry, and
  extension-inspection commands with deterministic table/JSON output, added a
  dedicated observability test suite, and relaxed scheduler imports so missing
  legacy models no longer break automation entry points.
- 2025-11-04: Hardened API startup orchestration with abort summaries and skip
  telemetry, restored Makefile tabs so `make health` and related DX targets run
  reliably, and expanded regression coverage/docs for the new startup manager.
- 2025-11-03: Added health-check latency/status metrics, an observability
  snapshot API (`apps.observability.diagnostics.collect_observability_snapshot`),
  and the `macli observe` command. Shipped the `ops:resilience` reference
  extension with an incident playbook contract, taught the extension scaffolder
  to generate observability contracts on demand, and introduced a scripted
  `make quality-gate` wrapper for lint/type/test/security automation.
- 2025-11-02: Hardened scenario plan parsing by preserving union-aware type
  checks, normalising byte-string tags, and backfilling loader regression tests
  so plan defaults reject non-string values before reaching provider
  orchestration.
- 2025-11-01: Promoted scenario plan parsing to the application layer with
  shared coverage summaries, added `macli inspect-plan`, exposed a
  `/snapshot/plans/preview` endpoint, refreshed the Streamlit console with a
  plan preview tab, and documented the workflow across README, examples, and
  stewardship guides.
- 2025-10-31: Added an async-aware scenario telemetry context manager with
  regression tests, decoupled cache observer typing to avoid circular
  initialisation, fixed Makefile tab alignment so `make ci` runs cleanly, and
  documented the new instrumentation in stewardship records.
- 2025-10-30: Instrumented scenario orchestration with dedicated Prometheus
  metrics and tracing, introduced extension contract discovery via
  `macli inspect-contracts` and `/extensions/contracts`, shipped the
  `scenarios:variance` reference extension, and added `make release` plus a
  release manager utility to bump versions and seed changelog/release notes.
- 2025-10-29: Normalised timezone handling and collections imports across the
  observability and domain layers, simplified deprecated snapshot/telemetry
  shims, tightened scenario batch orchestration utilities, refreshed CLI/test
  helpers, and raised the tooling line length budget so linting aligns with the
  modernised codebase.
- 2025-10-28: Simplified the ledger CSV ingestion helpers, taught the audit
  metrics CLI to reuse cached trace coverage, refreshed stewardship docs with
  updated quality metrics, and documented telemetry monitoring roles for agents.
- 2025-10-27: Instrumented extension loading with Prometheus counters/gauges,
  added a `/health/telemetry` endpoint plus `macli inspect-extensions`, shipped
  the `ops:heartbeat` reference extension, and refreshed architecture and
  automation guides for the new observability pipeline.
- 2025-10-26: Hardened audit provenance helpers with UTC defaults, stabilised
  tracing exporter fallbacks, polished the Streamlit console UX, and refreshed
  release tooling scripts/tests for lint compliance.
- 2025-10-25: Added a `tools.audit_metrics` CLI with a `make audit` wrapper for
  trace-based coverage snapshots, simplified trace header formatting, and
  refreshed automation docs to guide stewardship agents.
- 2024-11-07: Added an application-wide tracing subsystem with middleware,
  CLI instrumentation, and a tracing health probe; introduced an extension
  scaffolding command (`macli scaffold-extension`), shipped a cashflow reference
  extension, and documented the new operations playbooks for agents.
- 2024-11-06: Hardened telemetry provider error handling to log missing
  observability modules, propagate unexpected import failures, and extend
  regression coverage so instrumentation issues surface during testing.
- 2024-11-05: Added provider-backed snapshot orchestration via the `SnapshotOrchestrator`,
  exposing a new `/snapshot` API route and `macli snapshot` command with shared
  rendering utilities, provider provenance, and cache metrics.
- 2024-11-04: Added Prometheus-compatible metrics, health probes, and extension
  scaffolding. Shipping CLI tooling (`macli health`, `macli extensions`),
  Makefile quality gates, and companion docs (`docs/architecture/overview.md`,
  `docs/guides/extension_guide.md`, `docs/operations/automation_playbook.md`) to
  stabilise long-term operations.
- 2024-11-03: Hardened snapshot caching by enforcing lint/type compliance,
  capturing deterministic coverage artifacts, and documenting verification
  outputs for release readiness.
- 2024-11-02: Documented architecture/dependency posture, added CLI table
  output with validation, cached snapshot adapter calls, and expanded tests to
  cover caching plus UX flows.
- 2024-11-01: Refocused the project on portable modular accounting with domain models, adapter protocols, an in-memory demo CLI, refreshed documentation, and an initial license notice that has since been replaced by Apache-2.0.
- 2024-10-25: Comprehensive documentation sweep adding module docstrings for
  built-in plugins, expanding README/architecture/configuration references with
  usage examples, and aligning AI/forecasting/tax guides for contributor
  onboarding.
- 2024-10-24: Harden structured logging by normalising Uvicorn loggers, adding async context helpers, and extending regression coverage/documentation for the observability pipeline.
- 2024-10-23: Introduced structured logging with correlation IDs across the API, scheduler, and CLI plus configurability for log format and supporting regression tests/documentation updates.
- 2025-10-18: Use timezone-aware UTC datetimes across the codebase for audit, workflow, budget, and security timestamps. This reduces deprecation warnings from third-party libraries and ensures JWT expiries and serialized timestamps include timezone info.
- 2025-10-18: Harden authentication with rate-limited `/auth/token`, audit logging for all attempts, and scheduler lifecycle guards. Added AI interface documentation and refreshed architecture notes.
- 2024-10-19: Establish repository governance, developer tooling (pre-commit, EditorConfig, commitlint), and CI/CD scaffolding (GitHub Actions, Renovate) without behavioural changes.
