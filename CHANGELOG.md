# Changelog

## Unreleased

- 2024-11-04: Added Prometheus-compatible metrics, health probes, and extension
  scaffolding. Shipping CLI tooling (`macli health`, `macli extensions`),
  Makefile quality gates, and companion docs (`ARCHITECTURE_OVERVIEW.md`,
  `EXTENSION_GUIDE.md`, `AUTOMATION.md`) to stabilise long-term operations.
- 2024-11-03: Hardened snapshot caching by enforcing lint/type compliance,
  capturing deterministic coverage artifacts, and documenting verification
  outputs for release readiness.
- 2024-11-02: Documented architecture/dependency posture, added CLI table
  output with validation, cached snapshot adapter calls, and expanded tests to
  cover caching plus UX flows.
- 2024-11-01: Refocused the project on portable modular accounting with domain models, adapter protocols, an in-memory demo CLI, refreshed documentation, and a proprietary license notice.
- 2024-10-25: Comprehensive documentation sweep adding module docstrings for
  built-in plugins, expanding README/architecture/configuration references with
  usage examples, and aligning AI/forecasting/tax guides for contributor
  onboarding.
- 2024-10-24: Harden structured logging by normalising Uvicorn loggers, adding async context helpers, and extending regression coverage/documentation for the observability pipeline.
- 2024-10-23: Introduced structured logging with correlation IDs across the API, scheduler, and CLI plus configurability for log format and supporting regression tests/documentation updates.
- 2025-10-18: Use timezone-aware UTC datetimes across the codebase for audit, workflow, budget, and security timestamps. This reduces deprecation warnings from third-party libraries and ensures JWT expiries and serialized timestamps include timezone info.
- 2025-10-18: Harden authentication with rate-limited `/auth/token`, audit logging for all attempts, and scheduler lifecycle guards. Added AI interface documentation and refreshed architecture notes.
- 2024-10-19: Establish repository governance, developer tooling (pre-commit, EditorConfig, commitlint), and CI/CD scaffolding (GitHub Actions, Renovate) without behavioural changes.
