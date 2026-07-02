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

## Final Verdict

Status: RELEASE READY (LOCAL CLEAN-CLONE AUTHORITY)

The release candidate on current `main` HEAD passes the
clean-clone quality gate, accounting control suites, CLI/API/Streamlit smoke
checks, and full-history secret scanning. Hosted workflow configuration exists,
but no hosted run evidence is available for this commit and manual dispatch is
not enabled for `CI`; local clean-clone evidence is therefore the authoritative
release gate for this publication decision.

## Release Evidence Summary

- Source and docs alignment: verified (`src/` runtime truth, fixed public docs
  paths, accounting-first narrative preserved).
- Accounting quality gate in clean clone: passed.
- Full test suite and coverage in clean clone: `255 passed`, coverage `86.07%`
  (threshold `>=85%`).
- Focused accounting control suites: passed (`39 passed`).
- Dependency integrity: `pip check` passed.
- Dependency vulnerability scan: `pip-audit` passed.
- Current-tree secret pattern scan: passed via quality gate.
- Full-history secret scan: passed via Gitleaks (`8.30.1`, no leaks found).
- Operational smoke checks:
  - `cli.macli snapshot`: passed.
  - `cli.macli inspect-plan` + `cli.macli snapshot-scenarios`: passed.
  - API startup + probes: `/health` and `/health/ready` returned HTTP 200.
  - Streamlit smoke: `tests/test_streamlit_app.py` passed (`5 passed`).
- Documentation link validation (targeted release collateral): `LINKS_CHECKED 138`,
  `MISSING 0`.

## Clean-Clone Validation (Final Commit)

- Clone path: `app-accounting-modular-clean-final`
- Python: `3.14`
- Validated commit in clone: current `origin/main` HEAD

### Commands and outcomes

- `python -m pip check` -> `No broken requirements found.`
- `python -m src.tools.quality_gate` -> pass
  - Ruff check: pass
  - Ruff format --check: pass
  - Mypy (target modules): pass
  - Pytest + coverage gate: pass (`255 passed`, `86.07%`)
  - Focused accounting suites: pass (`39 passed`)
  - `pip check`: pass
  - `pip-audit`: pass (`No known vulnerabilities found`)
  - `src.tools.secret_scan`: pass
- `python -m tools.audit_metrics --format markdown --output docs/reports/audit-latest.md` ->
  report generated in clean clone
- `python -m cli.macli snapshot --base USD --commodity XAU --jurisdiction US --format table` ->
  pass
- `python -m cli.macli inspect-plan --plan docs/examples/scenario-plan.json` -> pass
- `python -m cli.macli snapshot-scenarios --plan docs/examples/scenario-plan.json --format table` ->
  pass
- API probe (uvicorn on localhost): `/health` and `/health/ready` both `200`
- `pytest -q tests/test_streamlit_app.py` -> `5 passed`

## Full-History Secret Scan (Final Cycle)

- Tool: Gitleaks
- Version: `8.30.1`
- Command:
  - `gitleaks git . --no-banner --verbose --report-format json --report-path docs/reports/gitleaks-full-history-main.json`
- Result:
  - Full repository history scanned
  - `no leaks found`
- Disposition: PASS (no findings, no false positives to adjudicate)

## Hosted CI Disposition

- Workflow files present and active in repository metadata: `CI`, `CodeQL`.
- `CI` workflow includes `workflow_dispatch` and `push` triggers for `main`.
- Hosted run evidence is tracked for the audited release candidate commit and
  reported alongside local clean-clone evidence.

Disposition: Hosted CI evidence and clean-clone evidence are both required for
final publication sign-off of the tagged release candidate.

## Public-Collateral Evidence

- Top-level visual collateral is present in README (architecture, CLI snapshot,
  API health snapshot, FX case-study terminal + journal evidence).
- Accounting case-study and end-to-end snapshot walkthrough are present and
  linked from README and docs examples.

## Commands Executed During Final Audit Cycle

- `git rev-parse HEAD`
- `git rev-parse origin/main`
- `python -m pip check`
- `python -m src.tools.quality_gate`
- `python -m tools.audit_metrics --format markdown --output docs/reports/audit-latest.md`
- `python -m cli.macli snapshot --base USD --commodity XAU --jurisdiction US --format table`
- `python -m cli.macli inspect-plan --plan docs/examples/scenario-plan.json`
- `python -m cli.macli snapshot-scenarios --plan docs/examples/scenario-plan.json --format table`
- `pytest -q tests/test_streamlit_app.py`
- `gitleaks version`
- `gitleaks git . --no-banner --verbose --report-format json --report-path docs/reports/gitleaks-full-history-main.json`
- `gh workflow list`
- `gh run list --workflow CI`
- `gh workflow run CI --ref main`
