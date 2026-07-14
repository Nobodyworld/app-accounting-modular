# Public Release Audit — Early Beta / Portfolio Preview

**Audit date:** 2026-07-14  
**Validated runtime baseline:** `b1ae2c12486484f406be6cf424cb14f0341f18ec`  
**Repository visibility:** public

## Classification

**EARLY BETA / PORTFOLIO PREVIEW**

Modular Accounting is a public code-portfolio demonstration of auditable accounting-control architecture. Demo providers use controlled sample data unless external credentials are configured.

The project is not an ERP, production tax engine, bank-feed product, treasury platform, regulated financial product, or commercially supported accounting system. Users must independently validate accounting, tax, security, data, provider, and deployment behavior before relying on any result.

## Published baseline

### PR #66 — publication preparation

- Squash merge: `d2e7b72861f4138fe8d14fabc7025b2e2de05cbb`
- Added the Early Beta / Portfolio Preview status block.
- Removed the unverified security mailbox and fixed response-time promises.
- Directed private reports to GitHub Private Vulnerability Reporting.

### PR #67 — post-publication audit alignment

- Squash merge: `77f1707baabdcb9b2de4c8a3b4e0f8ed24735b45`
- Recorded the completed publication-preparation baseline.
- Removed stale pre-merge publication instructions.

### PR #68 — actionable coverage evidence

- Final head: `64e513b5c7516678d420dfcad11b81f4564f611e`
- Squash merge: `b1ae2c12486484f406be6cf424cb14f0341f18ec`
- Hosted workflow run: `29310216173`
- Python 3.12, 3.13, and 3.14: passed.
- Container smoke: passed.
- Full pytest: 287 tests passed.
- Focused accounting-control suites: 52 tests passed.
- Release-authoritative line coverage: 86.12% (`5574/6472` statements).
- Branch coverage evidence: 67.55% (`997/1476` branches).
- Ruff lint and formatting, targeted mypy, `pip check`, `pip-audit`, and current-tree secret scan: passed.
- Per-version XML, JSON, audit, and quality-gate log artifacts: uploaded with 14-day retention.

## Prior accounting and release validation

### PR #60 — accounting integrity

- Squash merge: `9c45cc001449b38fec67d40474a38689ed81b2ac`
- Workflow run: `29176805053`
- Python 3.12, 3.13, and 3.14: passed.
- Accounting controls require valid double-entry postings, validate sides and amounts, balance each currency independently, roll back failed persistence, and report missing FX rates.

### PR #55 — release and container hardening

- Squash merge: `1b5d2f24a044c8939c90f7c9de611e08545d5506`
- Combined workflow run: `29176974979`
- Python 3.12, 3.13, and 3.14: passed.
- Compose validation, image builds, startup, API health, Streamlit health, status inspection, and teardown: passed.

## Coverage policy

The release-authoritative metric is aggregate **line coverage**, with a minimum of 85%.

Branch coverage is measured and retained as diagnostic evidence. It is not currently a release threshold. `coverage.xml`, `coverage.json`, and the complete quality-gate log are retained per supported Python version. Package-level values in `docs/reports/audit-latest.md` use Python `trace` and are stewardship diagnostics, not pytest-cov percentages.

## Security and automation posture

- `docs/SECURITY.md` directs reporters to **Security → Report a vulnerability** and preserves coordinated-disclosure guidance.
- The owner confirmed that GitHub Private Vulnerability Reporting, secret scanning, and push protection were enabled after publication.
- No unverified security email address is documented.
- The workflow token is limited to `contents: read`.
- GitHub Actions are pinned to full-length commit SHAs.
- Dependabot runs weekly with grouped minor/patch updates and open-PR limits of 3 for pip, 2 for Actions, and 1 for Docker.
- Recorded full-history Gitleaks validation reported zero findings.
- PR #52 removed the vulnerable `python-jose` dependency path in favor of `PyJWT[crypto]`.

## Remaining non-blocking work

- Issue #59 remains open for critical-module or diff-coverage policy and additional tax, budget, workflow, scheduler, and API failure-path tests.
- Repository description, topics, social preview, `main` rulesets, required checks, and least-privilege Actions settings should remain under periodic owner review.
- Version `0.1.0` remains unreleased. No tag or GitHub release is authorized by this audit.

Public visibility does not make the project production-ready. This audit supports code-portfolio review only and is not a certification for financial reporting, tax compliance, treasury execution, regulated data processing, or production deployment.
