# Public Release Audit

- Repository: app-accounting-modular
- Audit date: 2026-06-22
- Branch audited: main
- Auditor mode: direct-to-main, no PR

## Scope

This Phase 1 audit evaluates repository readiness for employer-facing public release and identifies release blockers without bundling major implementation changes.

## Safety Preconditions (Verified)

- main branch confirmed.
- Working tree was clean before edits.
- git pull --ff-only origin main succeeded.
- Annotated rollback tag created and pushed:
  - public-release-baseline-2026-06-22

## Repository Snapshot

- Python-centric modular accounting codebase with:
  - src/apps, src/cli, src/plugins, src/tools
  - tests and docs
  - top-level apps directory containing web/react-ui placeholders
- Core metadata present:
  - pyproject.toml
  - requirements.txt
  - requirements-dev.txt
  - Makefile
  - .github/workflows/ci.yml
  - .github/workflows/codeql.yml
- License file exists: LICENSE.

## Findings By Area

### 1) Current files and structure

- Source of truth appears to be under src/.
- A separate top-level apps/ directory also exists and can cause path ambiguity in docs and onboarding.

Status: Partial

### 2) Full Git history (high-level)

- main is active and current.
- Recent history includes extensive refactors, docs updates, test expansions, and provider/plugin additions.

Status: Partial

### 3) Secrets and credentials

- History filename scan found expected .env.example references.
- No obvious committed private-key filenames were identified in quick scan.

Status: Partial (deep content-level scan pending)

### 4) Personal/private information

- No direct PII artifacts identified in quick review.

Status: Partial

### 5) Generated files and hygiene

- Local generated directories exist in working tree (.venv, .pytest_cache, .ruff_cache).
- Quick tracked-file pattern check found no obvious tracked generated roots.

Status: Partial

### 6) Dependency vulnerabilities

- Makefile currently relies on safety for security checks.
- No current vulnerability report artifact was captured in this audit pass.

Status: Not Yet Verified

### 7) Licensing

- LICENSE exists.
- No license replacement requested or performed.

Status: Verified (presence only)

### 8) Broken documentation links

- Link validation command output not captured yet.

Status: Not Yet Verified

### 9) Build and runtime instructions

- pyproject toolchain targets Python 3.11.
- CI matrix targets Python 3.11.
- Runtime policy appears internally consistent at audit time.

Status: Verified

### 10) CI and quality gates

- CI workflow exists and runs pre-commit, pytest, and audit report generation.
- Makefile quality gate surfaces lint, typecheck, tests, and safety check.

Status: Partial

### 11) Public-release blockers

Potential P0/P1 blockers to confirm in next phases:

- P0 candidate: Documentation/code path ambiguity between top-level apps/ and src/apps/ may mislead setup and architecture claims.
- P0 candidate: Need proof accounting controls are correct and test-enforced for journal integrity and financial calculations.
- P1 candidate: Security gate currently tied to safety tool; evaluate whether dependency audit and secret scanning are complete for current employer/public standards.
- P1 candidate: Employer-facing docs should classify capabilities as Verified, Experimental, Partial, or Planned.

## Next-Phase Remediation Plan

1. Phase 2 (CI/build truth)
- Validate and harden quality/security gates under local-validation policy.
- Confirm tests fail fast and coverage thresholds match documented claims.

2. Phase 3 (critical fixes)
- Correct any incorrect source/documentation paths.
- Add or tighten accounting control tests (journal balancing, currency handling, data integrity paths).

3. Phase 4 (employer-facing docs)
- Update README and docs to only claim behavior that is actually validated.

4. Phase 5 (clean-clone validation)
- Run full documented workflow in a clean clone and record pass/fail truth.

## Commands Executed During Audit

- git rev-parse --abbrev-ref HEAD
- git status --porcelain
- git pull --ff-only origin main
- git tag -a public-release-baseline-2026-06-22 -m "Baseline before employer portfolio cleanup"
- git push origin public-release-baseline-2026-06-22
- git log --oneline --decorate -n 20
- git remote -v
- metadata and workflow inspections

## Local-validation policy note

GitHub Actions may be disabled by owner policy for this repository tier. Local validation and clean-clone validation are treated as authoritative for this preparation pass.
