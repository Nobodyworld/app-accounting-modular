# Stewardship Report

## Current Verdict

The repository is near public-ready, but should remain private until the release
evidence gaps in [`../../PUBLIC_RELEASE_AUDIT.md`](../../PUBLIC_RELEASE_AUDIT.md)
are closed. Current status: `KEEP PRIVATE - NEAR READY`.

## Metrics Overview

| Metric | Current Evidence | Notes |
| --- | --- | --- |
| Local quality gate | Pass | `python -m src.tools.quality_gate` passed in the latest Python 3.14 local run. |
| Test result | 244 passing tests | Includes the full suite plus focused accounting-control suites. |
| Coverage | 86.15% | Above the 85% release gate threshold. |
| Python policy | 3.12 minimum, 3.14 primary | Workflow matrix covers Python 3.12, 3.13, and 3.14. |
| License posture | Apache-2.0 with `NOTICE` attribution | Canonical license text restored in `LICENSE`; attribution moved to `NOTICE`. |
| Publication status | Keep private | Full-history secret scan and final clean-clone validation are pending. |

## Strengths

- Clear toolkit scope: accounting snapshots, provider adapters, journal controls,
  CLI/API surfaces, provenance, and scenario workflows.
- Strong accounting evidence in the foreign-currency case study, including
  invoice recognition, month-end remeasurement, settlement, and realized versus
  unrealized FX loss handling.
- Quality automation covers Ruff, Ruff format, mypy, pytest with coverage,
  focused accounting-control tests, `pip check`, project-scoped `pip-audit`, and
  the lightweight current-tree secret scanner.
- Runtime path truth is now documented as `src/apps/`, `src/cli/`,
  `src/plugins/`, and `src/tools/`; top-level `apps/` is documented as frontend
  placeholder territory.

## Remaining Release Evidence

- Run Gitleaks or an equivalent full-history secret scanner and record the tool
  version, command, commits scanned, findings, false-positive disposition, and
  final pass/fail result.
- Clean-clone validate the final publication commit with dependency
  installation, quality gate, full tests and coverage, accounting-control suites,
  audit generation, CLI snapshot, API startup, and Streamlit smoke test.
- Record hosted GitHub Actions success for the final commit, or explicitly state
  that hosted Actions are disabled and local clean-clone validation is the
  authoritative release gate.
- Improve first-screen employer-facing visual evidence with an architecture
  diagram, CLI snapshot, API or Streamlit screenshot, and foreign-currency
  journal image.

## Automation Handover

- Use `python -m src.tools.quality_gate` for the canonical local gate.
- Use `make audit` to regenerate `docs/reports/audit-latest.md`.
- Use `python -m cli.macli inspect-extensions`,
  `python -m cli.macli inspect-contracts`, and `python -m cli.macli observe` to
  capture extension and telemetry readiness after setting `PYTHONPATH` to
  include `src`.
- Keep `PUBLIC_RELEASE_AUDIT.md`, `docs/DEPENDENCIES.md`, and this report in
  sync whenever release evidence changes.

## Short-Term Roadmap

- Complete TASK-0089 through TASK-0092 in the root `TASKLIST.md`.
- Replace the dynamic `pip-audit` install in the quality gate with the pinned
  development dependency.
- Add visual release collateral to the README and case-study entry points.
- Create a versioned public release only after the audit status moves from
  `KEEP PRIVATE - NEAR READY` to a verified release-ready state.

## Evolvability & Opportunities

- **Evolvability score:** 8/10. The architecture, extension system, accounting
  controls, and quality gate are strong, but release evidence and visual
  presentation still need closure.
- **Best next improvement:** complete the release evidence trail before adding
  new functional scope.
