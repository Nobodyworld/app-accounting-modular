# Reporting Overview

## Structure & Dependency Map

- **Services**: Runtime Python service packages live under `src/apps/`, including
 FastAPI routers, accounting domain models, extension registry code,
 observability helpers, and the Streamlit app.
- **Clients**: Operational CLIs live under `src/cli/`. The top-level `apps/`
 directory is retained for frontend placeholders and is not the Python runtime
 source of truth.
- **Plugins**: Provider integrations and reference operational extensions live
 under `src/plugins/` and are loaded through
 `src/apps/api/services/plugin_loader.py` and
 `src/apps/api/services/extension_loader.py`.
- **Tooling**: Python 3.12 is the minimum supported version, Python 3.14 is the
 primary development baseline, and the workflow matrix covers Python 3.12,
 3.13, and 3.14.

## Release Reporting Status

- Canonical status source: [`../../PUBLIC_RELEASE_AUDIT.md`](../../PUBLIC_RELEASE_AUDIT.md).
- Current verdict, validation totals, and hosted CI disposition are maintained
 in the audit log so this overview does not drift as commits evolve.
- Treat this document as process guidance; use the public audit file as the
 authoritative release-evidence record.

## Evidence To Record Before Publication

- Gitleaks or equivalent full-history scan: tool version, command, commits
 scanned, findings, false-positive disposition, and final pass/fail result.
- Clean-clone validation: dependency installation, quality gate, full tests and
 coverage, focused accounting-control suites, audit generation, CLI snapshot,
 API startup, and Streamlit smoke test.
- Hosted CI disposition: successful GitHub Actions run for the final commit, or
 explicit documentation that hosted Actions are disabled and clean-clone local
 validation is authoritative.

## Risk Notes

- Current-tree secret scanning is useful but does not inspect historical commits.
- CI configuration is credible, but configuration alone is not the same as a
 recorded hosted run for the release candidate.
- Visual evidence remains thin for portfolio review; top-level collateral should
 add architecture, CLI, API or Streamlit, and foreign-currency journal images.

## Verification Baseline

- `python -m src.tools.quality_gate` is the canonical local quality gate.
- `make audit` regenerates the latest audit artifact under `docs/reports/`.
- `PUBLIC_RELEASE_AUDIT.md` must be updated whenever release validation evidence
 changes.
