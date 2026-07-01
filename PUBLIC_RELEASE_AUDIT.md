# Public Release Audit

- Repository: app-accounting-modular
- Audit date: 2026-07-01
- Branch audited: main
- Commit reviewed: `71ff89a17c45e4c2cf09399e6801a0464d951e3d`
- Auditor mode: direct-to-main, no PR

## Scope

This audit records release-readiness evidence for public distribution, including
path correctness, accounting control coverage, CI quality gates, and clean-clone
validation. It distinguishes verified local evidence from items that still need
formal release evidence before the repository should be made public.

## Release Summary

- Source path truth is now standardized on `src/` runtime paths.
- Documentation path drift between `apps/` and `src/apps/` has been corrected in
  primary onboarding docs.
- The CI workflow is configured to run the accounting quality gate before
  artifact publication, but hosted GitHub Actions evidence for the current head
  is not yet recorded.
- Accounting controls now include dedicated journal and financial data tests.
- A foreign-currency accounting case study has been added for audit-style review.
- The canonical Apache-2.0 license text has been restored in `LICENSE`, with
  project attribution moved to `NOTICE`.
- Latest local quality-gate evidence reports 244 passing tests and 86.15%
  coverage on Python 3.14.

Status: KEEP PRIVATE - NEAR READY

Public release remains blocked until the final publication commit has recorded
evidence for a full-history secret scan and a clean-clone validation run. Hosted
CI for the current head must either be confirmed with a successful GitHub Actions
run or explicitly documented as disabled, with clean-clone local validation named
as the authoritative release evidence.

## Remaining Publication Blockers

- P0: Run and record a full-history secret scan with Gitleaks or an equivalent
  tool, including tool version, command, commits scanned, findings, false-positive
  disposition, and final pass/fail result.
- P0: Clean-clone validate the final publication commit
  `71ff89a17c45e4c2cf09399e6801a0464d951e3d` or its successor, including
  dependency installation, quality gate, full tests and coverage, accounting
  control suites, audit generation, CLI snapshot, API startup, and Streamlit
  smoke test.
- P1: Confirm hosted GitHub Actions status for the final commit, or document
  that hosted Actions are disabled and local clean-clone validation is the
  authoritative release gate.
- P1: Improve the first-screen visual evidence with an architecture diagram, CLI
  snapshot, Streamlit or API screenshot, and foreign-currency journal image near
  the top of the project collateral.

## Findings By Area

### 1) Source and documentation paths

- Runtime source-of-truth confirmed under `src/apps`, `src/cli`, `src/plugins`,
  and `src/tools`.
- Top-level `apps/` retained for frontend placeholders (`react-ui`, `web`) and
  documented as non-runtime Python source.

Status: Verified

### 2) CI and quality gates

- CI is configured to run `make quality-gate` as the main accounting gate.
- CI is also configured to run explicit accounting control suites:
  - `tests/test_ledger_service.py`
  - `tests/test_data_snapshot_service.py`
  - `tests/test_modular_accounting_snapshot.py`
  - `tests/test_modular_accounting_controls.py`

Status: Partial (workflow configuration verified; hosted run for the current
head not yet recorded)

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

- Dependency security is based on project-scoped `pip-audit` requirements
  scanning.
- The local quality gate also runs `src.tools.secret_scan`, a lightweight
  current-tree pattern scan that excludes Git history.
- No full-history Gitleaks or equivalent scan has been recorded for the current
  release candidate.

Status: Partial (dependency audit and current-tree scan recorded locally;
full-history secret scan still pending)

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

### Required final validation target

- Commit to validate before publication:
  `71ff89a17c45e4c2cf09399e6801a0464d951e3d` or its successor.
- Current clean-clone status for that commit: Pending.
- Required evidence:
  - Dependency installation from `requirements-dev.txt`.
  - `python -m src.tools.quality_gate`.
  - Full pytest coverage result and focused accounting-control suites.
  - `make audit` or equivalent audit generation.
  - CLI snapshot smoke test.
  - API startup smoke test.
  - Streamlit smoke test.

### Prior clean-clone evidence

- Recorded result (2026-06-27): Pass.
- Clean-clone rerun (2026-06-30): performed against
  `8823845d59940d1470c0c877912003f7fe185b40` in
  `app-accounting-modular-clean-8823845`.
- Initial rerun outcome: Fail.
  - `ruff format --check` reported repository-wide reformat requirements under
    Windows checkout line endings.
  - Full pytest step saw environment-sensitive timeout failures in
    multiprocessing logging and Streamlit AppTest flows.
  - `pip_audit` failed from transient PyPI network read timeout.
- Follow-up hardening applied:
  - Enforced LF checkout for Python files in `.gitattributes`.
  - Increased robustness timeouts in `tests/test_observability_logging.py` and
    `tests/test_streamlit_app.py`.
  - Increased `pip_audit` network timeout to 60 seconds in quality gate.

This prior clean-clone evidence is useful regression history, but it does not
validate the current release candidate.

### Current local gate evidence

- Environment: Windows local workspace, Python 3.14 virtual environment.
- Command used: `python -m src.tools.quality_gate`.
- Outcome: Pass.
- Notes:
  - Ruff, Ruff format check, mypy, pytest with coverage threshold, focused
    accounting suites, `pip check`, project-scoped `pip_audit`, and
    `src.tools.secret_scan` all passed.
  - Final gate reported 244 passed tests and 86.15% total coverage.
  - SQLite ResourceWarning cleanup was validated in the final gate output.

This local gate is strong evidence for the working tree, but it does not replace
clean-clone validation of the final publication commit.

### Remote and hosted CI evidence

- Local branch: `main`.
- Local HEAD when this audit was updated:
  `71ff89a17c45e4c2cf09399e6801a0464d951e3d`.
- Remote main reported in the readiness review:
  `71ff89a17c45e4c2cf09399e6801a0464d951e3d`.
- Hosted GitHub Actions result for this commit: Not recorded in this audit.
- Required disposition before publication: record a successful hosted run, or
  explicitly state that hosted Actions are disabled and identify clean-clone
  local validation as the authoritative release evidence.

## Commands Executed During Audit

- `git rev-parse --abbrev-ref HEAD`
- `git status --porcelain`
- `python -m src.tools.quality_gate`
- Apache-2.0 license text review and `NOTICE` attribution check
- Repository metadata and workflow inspections
- Documentation and source-path cross checks
- Targeted accounting control test review

## Local-Validation Policy Note

If hosted CI execution is unavailable due to repository policy, local clean-clone
validation plus documented quality-gate outputs may be treated as authoritative
for release readiness only when the final commit, command list, and results are
recorded in this audit.
