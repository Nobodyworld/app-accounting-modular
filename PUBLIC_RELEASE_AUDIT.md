# Public Release Audit — Early Beta / Portfolio Preview

**Historical audit date:** 2026-07-14  
**Historical validated runtime baseline:** `b1ae2c12486484f406be6cf424cb14f0341f18ec`  
**Current repository baseline:** `f8c8c5d1498c612cce4f50905362cd682310399e` (merged Close Workspace UX correction, PR #158, 2026-09-13)  
**Repository visibility:** public

> [!NOTE]
> This file preserves the original July public-release audit as historical evidence while identifying the current repository baseline separately. Later accounting-close, provider-governance, provider-author, rehearsal, Windows/browser, and UX-correction slices were validated in their own PRs and post-merge CI. This is a portfolio audit, not production certification.

## Classification

**EARLY BETA / PORTFOLIO PREVIEW**

Modular Accounting is a public code-portfolio demonstration of auditable accounting-control architecture. Demo providers use controlled sample data unless external credentials are configured.

The project is not an ERP, production tax engine, bank-feed product, treasury platform, regulated financial product, provider marketplace, or commercially supported accounting system. Users must independently validate accounting, tax, security, data, provider, and deployment behavior before relying on any result.

## Current repository acceptance

### Close rehearsal and UX completion — PRs #156 and #158

- Current `main`: `f8c8c5d1498c612cce4f50905362cd682310399e`.
- Accepted/final source tree: `ef27d6a559f493285e2f3237a42c35d9442a1b1e`.
- PR #156 delivered the accountant close rehearsal/pilot kit and passed supported-Windows plus physical-browser acceptance before merge.
- PR #158 corrected immediate non-lifecycle table refresh, immediate sanitized denial feedback, and active-tab preservation across Streamlit reruns.
- Final PR #158 supported-Windows acceptance reported Python 3.14.0, Streamlit 1.63.0, 17 focused tests, 896 full-suite tests, and actual Chrome 152 acceptance at 1440×1000 and 390×844.
- Denied self-approval acceptance recorded sanitized `CLOSE_CONFLICT`, HTTP 409, zero SQL write statements, all 32 persisted tables unchanged, and the request remaining `REQUESTED`.
- Final PR #158 hosted evidence passed Python 3.12/3.13/3.14, `container-smoke`, `container-supply-chain`, and changed-production coverage; 19/19 changed executable production lines were covered.
- Trusted-main post-merge run `34738382100` passed the Python matrix, accounting controls, container supply-chain checks, and main-only provenance/SBOM attestations.
- Human-accountant usefulness/friction review remains **NOT RUN** and is tracked in issue #159. Automated/AppTest/browser acceptance does not substitute for that human judgment.

### v0.5 Provider Author Kit — PR #149

- Squash merge baseline: `7361903dbc49011f671f4b756cafd3e5e7527e3a`.
- Source head accepted for merge: `317ff535ebe87a94af0d81f8888880e65eed7a9e`.
- Post-merge CI run: `33265376953`.
- Python 3.12, 3.13, and 3.14 quality gates and accounting controls passed.
- Container supply-chain build/start/health/least-privilege/SBOM evidence passed.
- Main-only API and web provenance plus SBOM attestations passed.
- PR acceptance reported 862 tests passed, 52 accounting controls passed, 88.78% aggregate line coverage, and all 29 then-configured critical-module floors passed.
- The executable provider trust source remains `settings.allowed_providers`; package installation, manifests, entry points, and persisted governance state do not authorize code execution.

Hosted artifacts are short-lived operational evidence. The SHA, run identifiers, acceptance metrics, and trust-boundary disposition are the durable record; artifact retention should not be mistaken for the lifetime of an audit conclusion.

## Published baseline

### PR #66 — publication preparation

- Squash merge: `d2e7b72861f4138fe8d14fabc7025b2e2de05cbb`.
- Added the Early Beta / Portfolio Preview status block.
- Removed the unverified security mailbox and fixed response-time promises.
- Directed private reports to GitHub Private Vulnerability Reporting.

### PR #67 — post-publication audit alignment

- Squash merge: `77f1707baabdcb9b2de4c8a3b4e0f8ed24735b45`.
- Recorded the completed publication-preparation baseline.
- Removed stale pre-merge publication instructions.

### PR #68 — actionable coverage evidence

- Final head: `64e513b5c7516678d420dfcad11b81f4564f611e`.
- Squash merge: `b1ae2c12486484f406be6cf424cb14f0341f18ec`.
- Hosted workflow run: `29310216173`.
- Python 3.12, 3.13, and 3.14 passed.
- Container smoke passed.
- Full pytest: 287 tests passed.
- Focused accounting-control suites: 52 tests passed.
- Release-authoritative line coverage: 86.12% (`5574/6472` statements).
- Branch coverage evidence: 67.55% (`997/1476` branches).
- Ruff lint/format, targeted mypy, `pip check`, `pip-audit`, and current-tree secret scan passed.

## Prior accounting and release validation

### PR #60 — accounting integrity

- Squash merge: `9c45cc001449b38fec67d40474a38689ed81b2ac`.
- Workflow run: `29176805053`.
- Python 3.12, 3.13, and 3.14 passed.
- Accounting controls require valid double-entry postings, validate sides and amounts, balance each currency independently, roll back failed persistence, and report missing FX rates.

### PR #55 — release and container hardening

- Squash merge: `1b5d2f24a044c8939c90f7c9de611e08545d5506`.
- Combined workflow run: `29176974979`.
- Python 3.12, 3.13, and 3.14 passed.
- Compose validation, image builds, startup, API health, Streamlit health, status inspection, and teardown passed.

## Coverage policy

The release-authoritative aggregate metric is **line coverage**, with a minimum of 85%.

Aggregate branch coverage is retained as diagnostic evidence without an aggregate release floor. Separately, the current critical-module policy enforces explicit line and branch floors; those branch floors are mandatory. Changed-production coverage is an additional enforced workflow gate. Package-level values in `docs/reports/audit-latest.md` use Python `trace` and are stewardship diagnostics, not pytest-cov percentages.

## Merge-enforcement review — 2026-09-06

Active ruleset `18912267` requires strict up-to-date checks for `build (3.12)`, `build (3.13)`, `build (3.14)`, `container-smoke`, `diff-coverage`, and `container-supply-chain`, all bound to GitHub Actions integration `15368`. It also preserves pull-request-only squash merging, linear history, resolved review threads, no force pushes, no branch deletion, and no bypass actors.

The authorized settings update added the existing `diff-coverage` and `container-supply-chain` jobs as required checks while preserving the prior settings. PR #154 records the settings readback and source-validation evidence.

## Security and automation posture

- `docs/SECURITY.md` directs reporters to **Security → Report a vulnerability** and preserves coordinated-disclosure guidance.
- GitHub Private Vulnerability Reporting, secret scanning, and push protection were owner-confirmed after publication.
- No unverified security email address is documented.
- Workflow tokens use least-privilege permissions appropriate to each job.
- GitHub Actions are pinned to full-length commit SHAs.
- Dependabot runs weekly with grouped update policies and bounded open-PR counts.
- Recorded full-history Gitleaks validation reported zero findings.
- PR #52 removed the vulnerable `python-jose` dependency path in favor of `PyJWT[crypto]`.

## Remaining non-blocking work

- Run the real human-accountant pilot in issue #159; fix only demonstrated workflow/control gaps.
- Refresh and review open Dependabot PRs independently from current `main`.
- Preserve the six-check merge-enforcement configuration and conservative workspace-hygiene policy.
- Periodically review repository description, topics, social preview, rulesets, required checks, and least-privilege Actions settings.
- Migration-managed schema bootstrapping, distributed auth controls, multi-writer database controls, public-hosting acceptance, marketplace/provider publication, and production web-client work are conditional future scope, not blockers for the current portfolio claim.
- No tag or GitHub Release is authorized by this audit unless separately approved.

Public visibility does not make the project production-ready. This audit supports code-portfolio review only and is not a certification for financial reporting, tax compliance, treasury execution, regulated data processing, provider distribution, or production deployment.