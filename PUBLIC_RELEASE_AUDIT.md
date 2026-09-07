# Public Release Audit — Early Beta / Portfolio Preview

**Historical audit date:** 2026-07-14  
**Historical validated runtime baseline:** `b1ae2c12486484f406be6cf424cb14f0341f18ec`  
**Current milestone baseline:** `7361903dbc49011f671f4b756cafd3e5e7527e3a` (merged v0.5 Provider Author Kit, 2026-08-29)  
**Repository visibility:** public

> [!NOTE]
> This file preserves the original July public-release audit as historical evidence. It is not a claim that the July baseline is the current product state. The current milestone baseline above includes later accounting-close, provider-governance, and provider-author-kit work that was validated separately in its pull requests and post-merge CI.

## Classification

**EARLY BETA / PORTFOLIO PREVIEW**

Modular Accounting is a public code-portfolio demonstration of auditable accounting-control architecture. Demo providers use controlled sample data unless external credentials are configured.

The project is not an ERP, production tax engine, bank-feed product, treasury platform, regulated financial product, or commercially supported accounting system. Users must independently validate accounting, tax, security, data, provider, and deployment behavior before relying on any result.

## Current milestone acceptance

### v0.5 Provider Author Kit — PR #149

- Squash merge / current milestone baseline: `7361903dbc49011f671f4b756cafd3e5e7527e3a`
- Source head accepted for merge: `317ff535ebe87a94af0d81f8888880e65eed7a9e`
- Post-merge CI run: `33265376953`
- Python 3.12, 3.13, and 3.14 quality gates and accounting controls: passed.
- Container supply-chain build/start/health/least-privilege/SBOM evidence: passed.
- Main-only API and web provenance plus SBOM attestations: passed.
- PR acceptance reported 862 tests passed, 52 accounting controls passed, 88.78% aggregate line coverage, and all 29 critical-module floors passed.
- The executable provider trust source remains `settings.allowed_providers`; package installation, manifests, entry points, and persisted governance state do not authorize code execution.

Hosted artifacts are short-lived operational evidence. The SHA, run identifiers, acceptance metrics, and trust-boundary disposition above are the durable milestone record; artifact retention should not be mistaken for the lifetime of the audit conclusion.

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
- Per-version XML, JSON, audit, and quality-gate log artifacts were uploaded with 14-day retention.

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

Branch coverage is measured and retained as diagnostic evidence. It is not currently a release threshold. Changed-production coverage and explicit critical-module floors are additional review gates in the current repository. Package-level values in `docs/reports/audit-latest.md` use Python `trace` and are stewardship diagnostics, not pytest-cov percentages.

## Security and automation posture

- `docs/SECURITY.md` directs reporters to **Security → Report a vulnerability** and preserves coordinated-disclosure guidance.
- The owner confirmed that GitHub Private Vulnerability Reporting, secret scanning, and push protection were enabled after publication.
- No unverified security email address is documented.
- Workflow tokens use least-privilege permissions appropriate to each job.
- GitHub Actions are pinned to full-length commit SHAs.
- Dependabot runs weekly with grouped update policies and bounded open-PR counts.
- Recorded full-history Gitleaks validation reported zero findings.
- PR #52 removed the vulnerable `python-jose` dependency path in favor of `PyJWT[crypto]`.

## Remaining non-blocking work

- Keep current repository merge enforcement aligned with documented acceptance gates, including changed-production coverage and the container supply-chain gate before removing any older equivalent check.
- Keep work-slice cleanup conservative: ignored status alone never proves a database, environment file, user-data path, or unknown artifact is disposable.
- Periodically review repository description, topics, social preview, rulesets, required checks, and least-privilege Actions settings.
- No tag or GitHub release is authorized by this audit unless separately approved.

Public visibility does not make the project production-ready. This audit supports code-portfolio review only and is not a certification for financial reporting, tax compliance, treasury execution, regulated data processing, or production deployment.
