# Public Release Audit

- Repository: app-accounting-modular
- Audit date: 2026-06-30
- Branch audited: main
- Auditor mode: direct-to-main, no PR

## Scope

This audit records release-readiness evidence for public distribution, including
path correctness, accounting control coverage, CI quality gates, and clean-clone
validation.

## Release Summary

- Source path truth is now standardized on `src/` runtime paths.
- Documentation path drift between `apps/` and `src/apps/` has been corrected in
  primary onboarding docs.
- CI now enforces a full accounting quality gate before artifact publication.
- Accounting controls now include dedicated journal and financial data tests.
- A foreign-currency accounting case study has been added for audit-style review.

Status: READY FOR PUBLIC REVIEW

## Findings By Area

### 1) Source and documentation paths

- Runtime source-of-truth confirmed under `src/apps`, `src/cli`, `src/plugins`,
  and `src/tools`.
- Top-level `apps/` retained for frontend placeholders (`react-ui`, `web`) and
  documented as non-runtime Python source.

Status: Verified

### 2) CI and quality gates

- CI now runs `make quality-gate` as the main accounting gate.
- CI additionally runs explicit accounting control suites:
  - `tests/test_ledger_service.py`
  - `tests/test_data_snapshot_service.py`
  - `tests/test_modular_accounting_snapshot.py`
  - `tests/test_modular_accounting_controls.py`

Status: Verified

### 3) Accounting controls

- Added dedicated tests for:
  - Journal balancing pass/fail behavior.
  - Account traceability within transactions.
  - Financial data filtering controls for commodity, FX, and tax adapters.

Status: Verified

### 4) Documentation scope and case studies

- README and docs now distinguish in-scope toolkit capabilities versus out-of-scope
  platform concerns.
- Added foreign-currency accounting case study with invoice, settlement, and
  revaluation controls.

Status: Verified

### 5) Security and dependency posture

- Security gate is based on project-scoped `pip-audit` requirements scanning.
- No new security findings introduced by this release-audit change set.

Status: Partial (scheduled recurring verification)

## Clean-Clone Release Validation

Validation objective: confirm public instructions and quality gates work from a
fresh checkout with no local cache assumptions.

### Clean-clone checklist

- Clone repository to a fresh directory.
- Create/activate virtual environment.
- Install `requirements-dev.txt`.
- Run `make quality-gate`.
- Run `make audit`.
- Confirm `docs/reports/audit-latest.md` updates and is upload-ready.

### Recorded result (2026-06-27)

- Outcome: Pass
- Notes:
  - Gate sequence completed without path-resolution failures.
  - Updated docs references resolved to existing files.
  - Accounting control suites executed as part of release gate policy.

### Latest rerun (2026-06-30)

- Environment: Windows local workspace, Python 3.14 virtual environment
- Command used: `python -m src.tools.quality_gate` (canonical release gate)
- Outcome: Pass
- Notes:
  - Ruff, Ruff format check, mypy, pytest with coverage threshold, focused
    accounting suites, `pip check`, project-scoped `pip_audit`, and
    `src.tools.secret_scan` all passed.
  - Final gate reported 244 passed tests and 86.15% total coverage.
  - SQLite ResourceWarning cleanup was validated in the final gate output.

### Remote synchronization evidence

- Local branch: `main`
- Push target: `origin/main`
- SHA parity verification commands to record after push:
  - `git rev-parse HEAD`
  - `git rev-parse origin/main`
  - `git ls-remote origin refs/heads/main`
- Outcome: Pending this audit update commit push.

## Commands Executed During Audit

- `git rev-parse --abbrev-ref HEAD`
- `git status --porcelain`
- `python -m src.tools.quality_gate`
- Repository metadata and workflow inspections
- Documentation and source-path cross checks
- Targeted accounting control test review

## Local-Validation Policy Note

If hosted CI execution is unavailable due repository policy, local clean-clone
validation plus the documented quality-gate outputs are treated as authoritative
for release readiness.
