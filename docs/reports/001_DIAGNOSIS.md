# Diagnostic Report

## Current Verdict

The repository is near public-ready, but should remain private until the release
evidence gaps in `PUBLIC_RELEASE_AUDIT.md` are closed. The current status is
`KEEP PRIVATE - NEAR READY`.

## Release Blockers

- **P0 - Full-history secret scan:** The repository has a lightweight
  current-tree scanner in `src/tools/secret_scan.py`, but no recorded Gitleaks
  or equivalent scan across prior commits.
- **P0 - Final clean-clone validation:** Prior clean-clone evidence covers
  `8823845d59940d1470c0c877912003f7fe185b40`; the current reviewed commit
  `71ff89a17c45e4c2cf09399e6801a0464d951e3d` still needs a documented
  clean-clone run.
- **P1 - Hosted CI disposition:** GitHub Actions workflows are configured, but
  a hosted result for the current head is not recorded. If hosted Actions are
  disabled, the audit should say so explicitly.
- **P1 - Visual review evidence:** The project should surface architecture, CLI,
  API or Streamlit, and foreign-currency journal images near the top-level
  collateral before publication.

## Strengths

- Modular accounting scope is clear: snapshots, provider adapters, journal
  controls, CLI/API surfaces, provenance, and batch scenarios.
- Local Python 3.14 quality-gate evidence reports 244 passing tests and 86.15%
  coverage.
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
