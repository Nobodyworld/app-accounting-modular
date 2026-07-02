# Diagnostic Report

## Current Verdict

Release verdict and blockers are maintained in `PUBLIC_RELEASE_AUDIT.md`.
Treat this diagnosis as historical context and use the audit file for current
publication status.

## Release Blockers

- **P0 - Full-history secret scan:** The repository has a lightweight
  current-tree scanner in `src/tools/secret_scan.py`, but no recorded Gitleaks
  or equivalent scan across prior commits.
- **P0 - Final clean-clone validation:** Ensure clean-clone evidence is
  recorded for the audited release candidate referenced in
  `PUBLIC_RELEASE_AUDIT.md`.
- **P1 - Hosted CI disposition:** GitHub Actions workflows are configured, but
  a hosted result for the current head is not recorded. If hosted Actions are
  disabled, the audit should say so explicitly.
- **P1 - Visual review evidence:** The project should surface architecture, CLI,
  API or Streamlit, and foreign-currency journal images near the top-level
  collateral before publication.

## Strengths

- Modular accounting scope is clear: snapshots, provider adapters, journal
  controls, CLI/API surfaces, provenance, and batch scenarios.
- Local quality-gate totals should be read from the latest audit evidence
  rather than fixed in this diagnosis snapshot.
- Python support policy is explicit: minimum 3.12, primary development 3.14,
  workflow matrix 3.12 through 3.14.
- Foreign-currency accounting case study provides concrete audit-style evidence
  for invoice recognition, remeasurement, settlement, and FX loss handling.

## Documentation State

- Runtime path guidance should point to `src/apps/`, `src/cli/`, and
  `src/plugins/` while preserving import examples such as `apps.api.main` and
  `cli.macli`.
- Release-facing docs should avoid saying public hardening is complete until
  full-history scanning and final clean-clone validation are recorded.
- Security docs should distinguish dependency auditing from repository-history
  secret scanning.

## Recommended Modes

- **Release Evidence** - capture full-history scan, clean-clone validation, and
  hosted CI disposition for the final publication commit.
- **Documentation Polish** - keep top-level docs concise, employer-facing, and
  explicit about implemented versus placeholder surfaces.
- **Visual Presentation** - add concrete screenshots/diagrams that show the
  toolkit and accounting evidence quickly.
