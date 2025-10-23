# Changelog

## Unreleased

- 2024-10-25: Comprehensive documentation sweep adding module docstrings for
  built-in plugins, expanding README/architecture/configuration references with
  usage examples, and aligning AI/forecasting/tax guides for contributor
  onboarding.
- 2024-10-24: Harden structured logging by normalising Uvicorn loggers, adding async context helpers, and extending regression coverage/documentation for the observability pipeline.
- 2024-10-23: Introduced structured logging with correlation IDs across the API, scheduler, and CLI plus configurability for log format and supporting regression tests/documentation updates.
- 2025-10-18: Use timezone-aware UTC datetimes across the codebase for audit, workflow, budget, and security timestamps. This reduces deprecation warnings from third-party libraries and ensures JWT expiries and serialized timestamps include timezone info.
- 2025-10-18: Harden authentication with rate-limited `/auth/token`, audit logging for all attempts, and scheduler lifecycle guards. Added AI interface documentation and refreshed architecture notes.
- 2024-10-19: Establish repository governance, developer tooling (pre-commit, EditorConfig, commitlint), and CI/CD scaffolding (GitHub Actions, Renovate) without behavioural changes.
