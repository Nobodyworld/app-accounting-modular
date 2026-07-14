# Public Release Audit — Early Beta / Portfolio Preview

**Audit date:** 2026-07-13  
**Current `main` before this correction:** `1b5d2f24a044c8939c90f7c9de611e08545d5506`  
**Publication branch:** `release/early-beta-publication`

## Classification

**EARLY BETA / PORTFOLIO PREVIEW**

This repository may be public as a code-portfolio preview after this documentation correction is merged. Public visibility is not a production release, certification, or representation that every open pull request has passed current validation.

Modular Accounting demonstrates auditable accounting-control architecture. Demo providers use controlled sample data unless external credentials are configured. The project is not an ERP, production tax engine, bank-feed product, treasury platform, or commercially supported accounting system. Users must independently validate accounting, tax, security, data, provider, and deployment behavior.

## Git and validation evidence

### Current `main`

- Commit: `1b5d2f24a044c8939c90f7c9de611e08545d5506`
- Commit message: `release: harden public-readiness documentation and containers (#55)`

### PR #55 — merged release hardening

- Final PR head: `360ad0c8941286f7b045d39884e5df729b5f86f9`
- Squash merge commit: `1b5d2f24a044c8939c90f7c9de611e08545d5506`
- Combined workflow run: `29176974979`
- Python 3.12, 3.13, and 3.14: passed
- Container smoke: passed
- Compose validation, image builds, service startup, API health, Streamlit health, status inspection, and teardown: passed

### PR #60 — merged accounting integrity

- Squash merge commit: `9c45cc001449b38fec67d40474a38689ed81b2ac`
- Final workflow run: `29176805053`
- Python 3.12, 3.13, and 3.14: passed
- Diagnostic validation: 281 tests passed
- Aggregate pytest coverage recorded at merge: 86.12%
- Issue #58: closed

The merged controls require valid double-entry postings, validate posting sides and amounts, balance each currency independently, roll back failed persistence, report missing FX rates, and include service, domain, API, and no-partial-write regression coverage.

### PR #65 — draft coverage evidence

PR #65 is a separate draft merge candidate. Its private-repository workflow attempts created jobs but started no steps and produced no usable logs. Those attempts are non-validation events, not code-test failures.

After visibility changes, rerun PR #65 CI. Require Python 3.12, 3.13, and 3.14, coverage artifact upload, accounting-control suites, and container smoke to pass before marking it ready or merging it.

## Quality and security controls

The merged quality gate runs Ruff lint and formatting, targeted mypy, full pytest with an 85% aggregate coverage floor, focused accounting-control suites, `pip check`, `pip-audit`, and current-tree secret scanning.

Recorded release evidence also includes Streamlit regression tests, documentation link validation, and full-history Gitleaks scanning with zero findings. PR #52 removed the vulnerable `python-jose` dependency path in favor of `PyJWT[crypto]`.

Package-level metrics in `docs/reports/audit-latest.md` use Python `trace`; they are stewardship diagnostics, not the pytest-cov release gate.

## Security reporting correction

The unverified `security@modular-accounting.dev` address and fixed response promises have been removed from `docs/SECURITY.md`.

The policy directs reporters to **Security → Report a vulnerability** for private submission and preserves coordinated-disclosure guidance. The owner must enable or verify GitHub Private Vulnerability Reporting during the visibility-change session. No replacement email is documented without owner confirmation that it exists and is monitored.

## Publication limitations

- No GitHub release or version tag is authorized.
- Public visibility does not make the project production-ready.
- Open pull requests retain their own CI and review requirements.
- PR #65 must remain draft until executable hosted validation passes.
- Users must independently validate all accounting, tax, security, and deployment behavior.

## Owner actions during and after visibility change

1. Merge this publication correction before changing visibility.
2. Change repository visibility to public as an Early Beta / Portfolio Preview.
3. Enable or verify GitHub Private Vulnerability Reporting.
4. Confirm description, topics, and social preview.
5. Confirm `main` branch protection or rulesets and required CI checks.
6. Confirm least-privilege Actions permissions.
7. Confirm Dependabot alerts and security updates.
8. Confirm secret scanning and push protection.
9. Keep version `0.1.0` unreleased and create no tag or GitHub release.
10. Manually dispatch `main` CI and rerun PR #65 CI.

This audit supports public code-portfolio visibility only. It is not a certification for financial reporting, tax compliance, treasury execution, regulated data processing, or production deployment.
