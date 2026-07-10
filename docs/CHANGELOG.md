# Changelog

## Unreleased

- 2026-07-10: Refreshed the public-release audit against baseline
  `b00b2d84d082e8d97ee9dba0cf366c1fbe6f21e1`, aligned release notes and
  roadmap status, corrected setup commands, repaired container build/runtime
  configuration, and added CI container smoke validation.
- 2026-07-08: Merged PR #54 to clean README-linked architecture and
  accounting-control workflow SVG connector geometry. Hosted CI run
  `28931509566` passed across Python 3.12, 3.13, and 3.14.
- 2026-07-08: Polished final public-showcase presentation after PR #52 by
  replacing visible provider-catalog `Stub` wording with demo/sample/illustrative
  labels, rebuilding README-linked architecture and accounting-control workflow
  SVGs, clarifying controlled sample provider data in the README, and refreshing
  public-release audit evidence.
- 2026-07-07: Refreshed final public-release audit evidence after the
  `actions/upload-artifact` v7.0.1 Dependabot update and recorded successful
  PR #51 and PR #52 CI evidence.
- 2026-07-02: Finalized public-release validation, including clean-clone
  quality-gate evidence, full-history Gitleaks scanning with no findings,
  operational CLI/API/Streamlit smoke validation, and hosted CI disposition.
- 2026-07-01: Corrected the Apache-2.0 license text, added `NOTICE`
  attribution, and reframed public-release documentation as pre-release
  readiness pending final validation and owner review.
- 2026-06-30: Fixed async audit worker concurrency initialization, scheduler
  and security test isolation regressions, stale XPASS expectations, and
  dependency-audit failures; passed the Python 3.14 quality gate.
- 2025-11-06: Reorganized documentation under architecture, governance, and
  operations sections, relocated audit artifacts, updated automation tooling,
  and annotated task records for stewardship visibility.
- 2025-11-05: Rebuilt `macli` health, telemetry, and extension-inspection
  commands with deterministic table/JSON output and expanded observability tests.
- 2025-11-04: Hardened API startup orchestration with abort summaries and skip
  telemetry, restored Makefile targets, and expanded startup regression coverage.
- 2025-11-03: Added health-check latency/status metrics, observability snapshot
  diagnostics, the `macli observe` command, the `ops:resilience` extension, and
  the consolidated quality-gate wrapper.
- 2025-11-02: Hardened scenario plan parsing, byte-string tag normalization,
  and loader validation before provider orchestration.
- 2025-11-01: Promoted scenario plans to application artifacts with shared
  summaries, CLI inspection, API preview, Streamlit preview, and documentation.
- 2025-10-31: Added async scenario telemetry, removed cache observer import
  cycles, repaired Makefile automation, and expanded tests.
- 2025-10-30: Added scenario metrics/tracing, extension contract discovery,
  the `scenarios:variance` reference extension, and release tooling.
- 2025-10-29: Normalized timezone and collections usage, simplified deprecated
  shims, refreshed scenario utilities, and aligned tooling line length.
- 2025-10-28: Modularized ledger CSV validation, improved audit-metrics reuse,
  and refreshed telemetry stewardship documentation.
- 2025-10-27: Instrumented extension loading, added telemetry health endpoints,
  introduced `macli inspect-extensions`, and shipped `ops:heartbeat`.
- 2025-10-26: Hardened audit timestamps and tracing fallbacks, polished the
  Streamlit interface, and refreshed release tooling tests.
- 2025-10-25: Added `tools.audit_metrics`, the `make audit` wrapper, and updated
  automation documentation.
- 2025-05-24: Added directory-level READMEs, refreshed repository navigation,
  tightened API typing/logging utilities, and aligned metadata tests.
- 2024-11-07: Added application-wide tracing, extension scaffolding, a cashflow
  reference extension, and operations documentation.
- 2024-11-06: Hardened telemetry provider error handling and regression coverage.
- 2024-11-05: Added provider-backed snapshot orchestration through the API and
  CLI with provenance, cache metrics, and consolidated financial data.
