# v0.2 Accountant Close Workspace security review

## Scope and baseline

- Feature baseline: `483e56675a2ce0b40747974edffd95b976af322c`.
- Correction starting head: `faa8d508b07823469d93b598766d53b02dc61056`; final correction SHA is recorded in the PR validation report after push.
- This document intentionally does not rewrite the historical post-UX audit as if v0.2 were included in that baseline.
- New trust-boundary assets: accounting periods, close cycles, checklist tasks, reconciliations, variance reviews, journal approvals/decisions, evidence metadata, `/close` routes, the protected Streamlit workspace, and the critical-module coverage policy.

## Authorization matrix

| Capability | Tenant member | Ledger manager | Administrator |
| --- | --- | --- | --- |
| Read period/cycle/readiness/control summaries | Yes | Yes | Yes |
| Prepare reconciliations, variances, approvals, and operational checklist | No | Yes | Yes |
| Generate/download evidence | No | Yes | Yes |
| Final close, reopen, cancel, restart, return-to-work, revoke approval | No | No | Yes |

Every action uses the persisted authenticated session and server-derived actor. Organization authorization occurs before resource lookup. A resource absent from the authorized organization returns a nondisclosing `404`; clients cannot provide trusted preparer, requestor, reviewer, decision, or close actor IDs.

## Accounting-control boundaries

`AccountingPeriod.status` is the authoritative inclusive posting lock. `period_lock.py` acquires the SQLite tenant-period writer gate before direct or workflow posting checks state; final close acquires the same gate before readiness. `auto_process=true` keeps ingest and posting in one transaction. A closed-period rejection is the stable `ACCOUNTING_PERIOD_CLOSED` `409`, with no new staged row, posting, journal, or audit record.

Separation of duties is explicit: a journal requestor cannot approve their own request; a reconciliation preparer cannot provide final approval; final close/reopen/cancel/restart/return-to-work require an administrator. Ready freezes operational data. Closed/cancelled cycles are service-level read-only. Reopen checks same-tenant inclusive overlaps before any transition or audit write.

## Input, output, and audit bounds

Central hard limits cover labels, names, notes, reasons, metadata, custom tasks, reconciliation and variance row counts, approval comments, pagination, evidence rows, and the 8 MiB evidence archive. Metadata uses the existing depth/key/node/string validator. Every close mutation stages a bounded semantic audit event under the trusted actor context; raw uploads, archive bytes, JWTs, passwords, credentials, environment state, stack traces, and unrestricted provider metadata are excluded.

The evidence service uses stable filenames and row order, canonical UTF-8 JSON, LF CSV, spreadsheet-safe text, normalized ZIP timestamps, and SHA-256 for every file. Exact cycle entity IDs scope audit references. Trial balance, reconciliation, variance-run/row, approval/decision, checklist, evidence, and audit queries consume one row budget and use `remaining + 1` overflow detection before ZIP serialization. Final close records evidence from the final `CLOSED` state in the same transaction.

## Failure, concurrency, and operational assumptions

- SQLModel `create_all` remains the repository's validated bootstrap; no unrelated migration platform was introduced.
- Unique/check/index constraints cover tenant labels, period date validity, one durable cycle per period, one reconciliation per account/cycle, stable task keys, and one current approval per cycle/reference.
- Critical writes use conditional SQL `UPDATE ... WHERE version/content_revision = expected` and require `rowcount == 1`; rollback removes failed audits and revision bumps.
- `CloseCycle.content_revision` is the evidence authority. It advances for lifecycle and child control mutations; failed writes do not advance it.
- SQLite's single-writer gate is the validated close/post serialization strategy. Multi-writer databases require database-native row locking or an equivalent gate before production use.
- Local loopback demonstration remains the validated deployment boundary. This review does not approve LAN/public hosting, regulatory use, or production financial close reliance.

## Release security evidence

- Both the hash-locked container dependency audit and development dependency audit report no known vulnerabilities. GitPython was narrowly updated from 3.1.57 to 3.1.58 after the final audit identified the fixed 2026 advisories.
- The repository secret scanner passes, and Gitleaks reports no leaks across 272 commits.
- The generated route inventory maps 70 method/path entries with no unmapped application routes and is byte-deterministic for a fixed commit.
- Docker was not installed in the final Windows validation environment, so Compose runtime validation remains delegated to CI or another host with Docker available; no container pass is claimed here.
