# v0.2 Accountant Close Workspace security review

## Scope and baseline

- Feature baseline: `483e56675a2ce0b40747974edffd95b976af322c`.
- Feature implementation head: `bab98ca037c71f1eb50cccea0e6981266dac3bf5` (domain/API and authenticated workspace commits; release-evidence documentation follows this SHA).
- This document intentionally does not rewrite the historical post-UX audit as if v0.2 were included in that baseline.
- New trust-boundary assets: accounting periods, close cycles, checklist tasks, reconciliations, variance reviews, journal approvals/decisions, evidence metadata, `/close` routes, the protected Streamlit workspace, and the critical-module coverage policy.

## Authorization matrix

| Capability | Tenant member | Ledger manager | Administrator |
| --- | --- | --- | --- |
| Read period/cycle/readiness/control summaries | Yes | Yes | Yes |
| Prepare reconciliations, variances, approvals, and operational checklist | No | Yes | Yes |
| Generate/download evidence | No | Yes | Yes |
| Final close, reopen, cancel, final approval, revoke approval | No | No | Yes |

Every action uses the persisted authenticated session and server-derived actor. Organization authorization occurs before resource lookup. A resource absent from the authorized organization returns a nondisclosing `404`; clients cannot provide trusted preparer, requestor, reviewer, decision, or close actor IDs.

## Accounting-control boundaries

`AccountingPeriod.status` is the authoritative inclusive posting lock. `period_lock.py` runs before direct `LedgerService` mutation and before `WorkflowService` validation/status/posting/audit mutation, including auto-post and retry paths. A closed-period rejection is the stable `ACCOUNTING_PERIOD_CLOSED` service exception mapped to a safe `409`. Focused tests assert no transaction, journal line, staged-status change, or audit entry remains after rejection.

Separation of duties is explicit: a journal requestor cannot approve their own request; a reconciliation preparer cannot provide final approval; final close/reopen/cancel require an administrator; ready and close both call the same readiness service; and reopen requires a nonempty bounded reason. A one-user demonstration remains blocked rather than bypassing these controls.

## Input, output, and audit bounds

Central hard limits cover labels, names, notes, reasons, metadata, custom tasks, reconciliation and variance row counts, approval comments, pagination, evidence rows, and the 8 MiB evidence archive. Metadata uses the existing depth/key/node/string validator. Every close mutation stages a bounded semantic audit event under the trusted actor context; raw uploads, archive bytes, JWTs, passwords, credentials, environment state, stack traces, and unrestricted provider metadata are excluded.

The evidence service uses stable filenames and row order, canonical UTF-8 JSON, LF CSV, the existing spreadsheet-safe text policy, normalized ZIP timestamps, and SHA-256 for every file. It persists only manifest metadata and rebuilds archive bytes in memory. The archive hard-fails when row or byte limits are exceeded.

## Failure, concurrency, and operational assumptions

- SQLModel `create_all` remains the repository's validated bootstrap; no unrelated migration platform was introduced.
- Unique/check/index constraints cover tenant labels, period date validity, one cycle per period, one reconciliation per account/cycle, stable task keys, single approval reference shape, nonnegative tolerances, bounded versions, and tenant-first access paths.
- Active-period overlap is checked transactionally at the service boundary. SQLite serializes writers within its supported locking model; multi-process databases would require a database-native exclusion constraint or equivalent migration before production use.
- Evidence generation and audit metadata recording are separate from raw archive persistence; the deterministic bundle excludes its own generation audit so repeated bytes for unchanged accounting state remain stable.
- Local loopback demonstration remains the validated deployment boundary. This review does not approve LAN/public hosting, regulatory use, or production financial close reliance.

## Release security evidence

- Both the hash-locked container dependency audit and development dependency audit report no known vulnerabilities. GitPython was narrowly updated from 3.1.57 to 3.1.58 after the final audit identified the fixed 2026 advisories.
- The repository secret scanner passes, and Gitleaks reports no leaks across 272 commits.
- The generated route inventory maps 68 method/path entries with no unmapped application routes and is byte-deterministic for a fixed commit.
- Docker was not installed in the final Windows validation environment, so Compose runtime validation remains delegated to CI or another host with Docker available; no container pass is claimed here.
