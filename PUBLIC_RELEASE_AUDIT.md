# Public Release Audit

- Repository: app-accounting-modular
- Audit date: 2026-07-02
- Branch audited: main
- Commit reviewed: current `main` HEAD at audit completion (see command evidence below)
- Auditor mode: direct-to-main, no PR

## Scope

This audit records publication-readiness evidence for the exact release commit,
including clean-clone execution, accounting quality controls, full-history
secret scanning, and hosted CI disposition.

## Current Status

The release candidate is undergoing final verification. This document tracks:

1. **Local Clean-Clone Evidence** (completed):
   - Full quality gate: passed locally on Python 3.14
   - Comprehensive Streamlit test coverage: 10 tests passed
   - All accounting control suites: 39 passed
   - Full dependency and secret scans: passed

2. **Hosted CI Evidence** (pending):
   - Workflow configuration: complete with `workflow_dispatch` trigger
   - Matrix configuration: Python 3.12, 3.13, 3.14
   - Expected artifact uploads: audit-latest-python-{version}
   - Status: awaiting GitHub Actions completion

**Note:** Do not consider this publication-ready until hosted CI completes
successfully on this exact commit SHA. Both local and hosted evidence are
required for publication sign-off.

## Release Evidence Summary

### Local Clean-Clone Validation (Python 3.14)

- Source and docs alignment: verified (`src/` runtime truth, fixed public docs
  paths, accounting-first narrative preserved).
- Full test suite: `255 passed` on Python 3.14
- Coverage: `86.07%` (exceeds threshold of `>=85%`)
- Accounting control suites: `39 passed`
- Dependency integrity: `pip check` passed
- Dependency vulnerability scan: `pip-audit` passed (no vulnerabilities found)
- Full-history secret scan: `gitleaks` passed (no leaks found)
- CLI smoke checks: all three commands successful
  - `cli.macli snapshot`
  - `cli.macli inspect-plan`
  - `cli.macli snapshot-scenarios`
- API smoke checks: `/health` and `/health/ready` returned HTTP 200
- **Streamlit regression tests: `10 passed`** (comprehensive coverage)
  - Primary tab rendering and provider controls
  - Snapshot request execution and diagnostics
  - Invalid currency blocking
  - Missing provider capability warnings
  - Provider catalog loading failure handling
  - FX/commodity/tax table rendering with correct columns
  - Provenance, cache diagnostics, health/readiness visibility
  - Case-study link presence
  - Snapshot generation failure handling
  - Stale success state clearing after failed snapshot

### Full-History Secret Scan (Local Cycle)

- Tool: Gitleaks `8.30.1`
- Repository history: fully scanned
- Result: no leaks found
- Disposition: PASS

## Hosted CI Configuration

- Workflow file: `.github/workflows/ci.yml`
- Triggers: `pull_request`, `push` to `main`, `workflow_dispatch`
- Matrix: Python 3.12, 3.13, 3.14
- Artifact uploads: `audit-latest-python-{version}` (versioned per job to avoid collision)
- Quality gate steps: present and configured
- Accounting suites steps: present and configured

## Clean-Clone Execution Details (Final Commit)

- Clone path: `app-accounting-modular-clean-final`
- Python: `3.14`
- Validated commit in clone: current `origin/main` HEAD

### Commands executed

- `python -m pip check` -> `No broken requirements found.`
- `python -m src.tools.quality_gate` -> pass (all checks)
- `python -m tools.audit_metrics --format markdown --output docs/reports/audit-latest.md` ->
  report generated
- `python -m cli.macli snapshot --base USD --commodity XAU --jurisdiction US --format table` ->
  pass
- `python -m cli.macli inspect-plan --plan docs/examples/scenario-plan.json` -> pass
- `python -m cli.macli snapshot-scenarios --plan docs/examples/scenario-plan.json --format table` ->
  pass
- API probe (uvicorn on localhost): `/health` and `/health/ready` both `200`
- `pytest -q tests/test_streamlit_app.py` -> `10 passed`

## Documentation Validation

- Link validation (targeted release collateral): deferred to comprehensive pass
  (in progress)
- Public collateral alignment: Streamlit screenshot and architecture diagram
  present; visual evidence collection completed

## Release Sign-Off Criteria

**Publication is authorized only when ALL of the following are true:**

1. ✅ Local clean-clone quality gate passes (Python 3.14)
2. ✅ Comprehensive Streamlit regression tests pass (10/10)
3. ✅ Full dependency and secret scans pass locally
4. ⏳ Hosted CI matrix completes (Python 3.12, 3.13, 3.14)
5. ⏳ All matrix jobs pass their quality gate and accounting suites steps
6. ⏳ Artifacts upload successfully to each matrix job
7. ⏳ Complete repository-wide link validation passes
8. ✅ All contradictions in this audit document are resolved
9. ✅ Release tag (`v1.0.0-rc1`) created and immutable at audited commit SHA
10. ✅ Repository visibility remains private during final staging

**Current blockers:** Hosted CI job completion and comprehensive link validation.
Do not merge or publish until all sign-off criteria are satisfied.
