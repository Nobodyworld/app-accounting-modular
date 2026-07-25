# Post-UX Pre-Release Security Audit

## Status

**In progress — no release-security conclusion has been reached.**

This report is the evidence record for issue #87. Existing CI, dependency audits,
secret scanning, browser acceptance, and prior remediations are inputs to this
audit; none is a substitute for completing the full audit scope.

## Exact audit target

- Repository: `Nobodyworld/app-accounting-modular`
- Branch: `security/post-ux-pre-release-audit`
- Audited `main` SHA: `926e0057cdc7676ac1cb006502a37fdf651bbb42`
- Audit branch starting SHA: `926e0057cdc7676ac1cb006502a37fdf651bbb42`
- Target date: 2026-07-25

If `main` changes, record the new SHA here before incorporating it. Restart any
check affected by the changed files or document why its existing evidence remains
valid. Never combine evidence from materially different trees without attribution.

## Documented operating model

The currently validated publication boundary is a local demonstration using
loopback-bound services and non-production data. This audit must separately assess:

1. local-only execution;
2. trusted-team workstation use;
3. LAN deployment;
4. container deployment behind an operator-controlled reverse proxy; and
5. direct or indirect public hosting.

No broader deployment mode is approved merely because a local or CI check passes.

## Evidence rules

Every executed check must record:

- exact commit SHA;
- operating system and relevant tool versions;
- exact command or reproducible procedure;
- result and output location;
- reviewed false positives;
- limitations, skipped checks, and assumptions;
- related finding or remediation issue when applicable.

Do not place credentials, access tokens, refresh tokens, JWT secrets, private test
data, raw environment dumps, or unredacted scanner output in the repository.

## Audit evidence index

| Area | Evidence | Status | Result / finding | Source |
|---|---|---:|---|---|
| Threat model and trust boundaries | Pending | Not started | — | — |
| Route inventory and authorization classification | Pending | Not started | — | — |
| Authentication and session negative tests | Pending | Not started | — | — |
| Tenant-isolation negative tests | Pending | Not started | — | — |
| Input, upload, error, and export safety | Pending | Not started | — | — |
| Persistence, rollback, concurrency, and idempotency | Pending | Not started | — | — |
| Provider and background-task boundaries | Pending | Not started | — | — |
| Network, browser, proxy, CORS, CSRF, and headers | Pending | Not started | — | — |
| Full-history secret scan | Pending | Not started | — | — |
| Dependency and supply-chain audit | Pending | Not started | — | — |
| GitHub configuration and full-SHA Actions review | Pending | Not started | — | — |
| Container and Compose runtime review | Pending | Not started | — | — |
| SBOM generation and review | Pending | Not started | — | — |
| Static security analysis | Pending | Not started | — | — |
| Dynamic API and container testing | Pending | Not started | — | — |
| Final severity and deployment disposition | Pending | Not started | — | — |

## Existing validated inputs

These items must be verified against the exact audit target where relevant, but
may be cited as prior evidence:

- PR #92: local Compose authentication and loopback-binding hardening;
- PR #94: audit actors bound to authenticated principals and authorized scope;
- PR #96: non-root, read-only, capability-dropped containers;
- PR #97: responsive authenticated Streamlit workflow, protected Scenario Plan
  Review, stale-state cleanup, browser acceptance, and manual keyboard acceptance;
- PR #100: plan-preview schema/default semantics and strict direct-batch contract;
- dependency/action updates #82, #84, #85, #103, and #104;
- hosted Python 3.12/3.13/3.14 quality gates, accounting controls, dependency
  audit, secret scan, and live container smoke evidence.

## Threat model and trust boundaries

### Assets

Document handling expectations for:

- passwords and password hashes;
- access and refresh tokens;
- JWT signing material and session identifiers;
- organization membership and tenant-scoped accounting data;
- ledgers, transactions, budgets, forecasts, reports, and audit records;
- provider configuration and externally sourced financial data;
- uploaded scenario plans and budget files;
- generated CSV and other exports;
- database files, cache state, logs, telemetry, and audit evidence.

### Trust boundaries

Inventory data and identity transitions among:

- browser and Streamlit;
- Streamlit and FastAPI;
- FastAPI dependencies and database sessions;
- tenant authorization and service-layer object lookup;
- provider registry, plugin loading, and external services;
- scheduler and background execution contexts;
- host filesystem, container writable mounts, and generated exports;
- reverse proxy, TLS termination, and forwarded headers.

### Attacker profiles and assumptions

Record realistic anonymous, authenticated cross-tenant, malicious tenant-member,
malicious administrator, compromised provider, local-user, and network attacker
capabilities. Explicitly state which host and reverse-proxy controls remain the
operator's responsibility.

## Route and authorization inventory

Create a complete route table containing:

| Method | Path | Classification | Tenant input | Authorization dependency | Data returned / changed | Negative tests |
|---|---|---|---|---|---|---|
| Pending | Pending | Public / authenticated / member / manager / admin | Pending | Pending | Pending | Pending |

The inventory must include health, authentication, audit, ledger, workflow,
reports, forecast, FX, market, tax, snapshot, scenario-plan, extension, and
provider surfaces.

## Required execution evidence

### Repository and history

Record results for:

```text
git status --short
git rev-parse HEAD
git log --oneline --decorate -n 20
git fsck --full
```

Run a full-history secret scan and record the scanner version, command, exclusions,
reviewed findings, and final disposition.

### Quality and accounting controls

Record the exact output of:

```text
python -m src.tools.quality_gate
pytest -q tests/test_ledger_service.py tests/test_data_snapshot_service.py tests/test_modular_accounting_snapshot.py tests/test_modular_accounting_controls.py
```

### Static security analysis

Use appropriate Python/FastAPI analysis, record tool versions and configuration,
and review every finding. Do not equate a zero-finding scanner run with proof of
security.

### Dependency and SBOM evidence

Record runtime and development dependency audits, dependency resolution, optional
extras, and an SBOM covering the audited application and container images.

### Dynamic and negative testing

Use loopback-only non-production services. Include malformed, expired, revoked,
wrong-type, and tampered tokens; cross-tenant identifiers; unauthorized direct API
calls; oversized and deeply nested inputs; unsafe filenames; CSV formula values;
duplicate and stale requests; provider failures; timeout behavior; concurrency;
and container/filesystem boundaries.

## Findings register

| ID | Severity | Title | Affected component | Evidence | Disposition | Issue |
|---|---|---|---|---|---|---|
| Pending | Critical / High / Medium / Low / Informational | Pending | Pending | Pending | Open / fixed / accepted | Pending |

Open one GitHub issue per actionable finding. Critical or High findings block any
broader release claim. Medium findings require remediation or explicit owner
acceptance with rationale.

## Deployment disposition

Complete only after the evidence and findings registers are final.

| Deployment mode | Decision | Required controls | Unsupported assumptions |
|---|---|---|---|
| Local demonstration | Pending | Pending | Pending |
| Trusted-team use | Pending | Pending | Pending |
| LAN deployment | Pending | Pending | Pending |
| Reverse-proxied container deployment | Pending | Pending | Pending |
| Public hosting | Pending | Pending | Pending |

## Final sign-off

- Audit SHA confirmed: Pending
- Evidence complete and reproducible: Pending
- Critical findings open: Pending
- High findings open: Pending
- Medium findings resolved or accepted: Pending
- Documentation updated: Pending
- Release/deployment statement approved by owner: Pending

This report must remain **In progress** until every completion criterion from issue
#87 is addressed with reproducible evidence.