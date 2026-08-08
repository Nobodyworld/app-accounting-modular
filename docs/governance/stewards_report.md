# Stewardship Report

## Current Verdict

Release classification and evidence are maintained in
[`../../PUBLIC_RELEASE_AUDIT.md`](../../PUBLIC_RELEASE_AUDIT.md). This report
summarises stewardship posture and should be interpreted alongside the current
audit verdict.

## Metrics Overview

| Metric | Current Evidence | Notes |
| --- | --- | --- |
| Local quality gate | Pass | `python -m src.tools.quality_gate` is the canonical local gate. |
| Test result | Refer to public audit | Totals are recorded in `PUBLIC_RELEASE_AUDIT.md` to avoid stale snapshots. |
| Coverage | Refer to public audit | Threshold and latest measured coverage are recorded in the audit. |
| Python policy | 3.12 minimum, 3.14 primary | Workflow matrix covers Python 3.12, 3.13, and 3.14. |
| License posture | Apache-2.0 with `NOTICE` attribution | Canonical license text is in `LICENSE`; attribution is in `NOTICE`. |
| Publication status | Refer to public audit | Release classification is controlled by the public audit verdict. |

## Strengths

- Clear toolkit scope: accounting snapshots, provider adapters, journal controls,
  CLI/API surfaces, provenance, and scenario workflows.
- Strong accounting evidence in the foreign-currency case study, including
  invoice recognition, month-end remeasurement, settlement, and realized versus
  unrealized FX loss handling.
- Quality automation covers Ruff, Ruff format, mypy, pytest with coverage,
  focused accounting-control tests, `pip check`, `pip-audit` against the hashed
  runtime lock, and the lightweight current-tree secret scanner.
- The v0.2 close tranche adds reviewable per-critical-module line and branch floors for ledger, workflow, persisted-session security, period lock, close lifecycle, reconciliation, evidence, and router modules; missing modules or branch evidence fail closed instead of being masked by aggregate coverage.
- Accountant close now has one server-derived readiness contract, inclusive service-level posting locks, explicit two-person approvals, deterministic spreadsheet-safe evidence, and a protected Streamlit workflow. These remain Early Beta controls rather than ERP, production close, compliance, or public-hosting claims.
- Central inbound resource policy bounds API bodies, expensive Pydantic
  collections, nested metadata, numeric controls, and retained Streamlit
  uploads while keeping rejected requests observable.
- Authentication sessions are persisted and enforced server-side; refresh
  credentials rotate once through a conditional digest swap, reuse revokes the
  complete session, and tenant administrators can revoke only same-organization
  member sessions.
- Network-backed providers enforce a centralized outbound trust boundary: 1 MiB
  streamed HTTP reads, 512 FX records, explicit connect/read timeouts, bounded
  selected-transient retries, sanitized provider errors, and a single bounded
  YFinance call with 10,000-day/row limits. Tests use stubs without live
  credentials. Independently, both application images use one verified official
  Python manifest digest and the same exact, hashed Python 3.14/Linux runtime
  graph. CI is designed to retain image archives, inventories, checksums, and
  SPDX SBOMs for pull requests and to publish archive-bound attestations only on
  trusted events.
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
- Use `python scripts/dependencies/verify_container_lock.py` for the normal
  offline freshness check. For an intentional refresh, use
  `pwsh scripts/dependencies/Generate-ContainerLock.ps1` on Windows or
  `sh scripts/dependencies/generate-container-lock.sh` on Linux, review all
  direct and transitive changes, run the focused supply-chain tests and
  `pip-audit`, and rebuild both images.
- Treat pull-request SBOMs, checksums, and archives as ordinary 14-day
  evidence. Verify provenance and SBOM attestations only for an eligible trusted
  `main` push or manual run; no registry artifact is published.
- Keep `PUBLIC_RELEASE_AUDIT.md`, `docs/DEPENDENCIES.md`, and this report in
  sync whenever release evidence changes.

## Short-Term Roadmap

- Review the first eligible trusted-event archive attestations after the
  workflow reaches `main`; pull-request runs cannot publish them by design.
- Add visual release collateral to the README and case-study entry points.
- Create a versioned public release only after the audit verifies hosted CI,
  clean-clone, and secret-scan evidence for the tagged candidate.

## Evolvability & Opportunities

- **Evolvability score:** 8/10. The architecture, extension system, accounting
  controls, and quality gate are strong, but release evidence and visual
  presentation still need closure.
- **Best next improvement:** complete the release evidence trail before adding
  new functional scope.
