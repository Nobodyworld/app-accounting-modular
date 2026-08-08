# v0.2 Accountant Close Workspace security review

## Scope and exact correction

- Required main baseline: `483e56675a2ce0b40747974edffd95b976af322c`.
- Required correction starting head: `a52afe320c1d8277c8d80b0a1b763ef7260bb034`.
- Corrected implementation and browser-test head: `48e1d3aea6678aa49c8ba973a4d43a697de3e012`.
- This document intentionally does not rewrite the historical post-UX audit as if v0.2 were included in that baseline.
- Trust-boundary assets are accounting periods and ledger-activity revisions, close cycles and typed policy, checklist tasks, reconciliations, variance runs/current rows, journal approvals/decisions, evidence metadata, `/close` routes, the protected Streamlit workspace, and the critical-module coverage policy.

## Authorization matrix

| Capability | Tenant member | Ledger manager | Administrator |
| --- | --- | --- | --- |
| Read period/cycle/readiness/control summaries | Yes | Yes | Yes |
| Create a cycle with server policy defaults | No | Yes | Yes |
| Prepare reconciliations, variances, approvals, and operational checklist | No | Yes | Yes |
| Generate/download evidence | No | Yes | Yes |
| Override policy or record not-applicable treatment, with reason | No | No | Yes |
| Final close, reopen, cancel, restart, return-to-work, revoke approval | No | No | Yes |

Every action uses the persisted authenticated session and server-derived actor. Organization authorization occurs before resource lookup. A resource absent from the authorized organization returns a nondisclosing `404`; clients cannot provide trusted preparer, requestor, reviewer, decision, or close actor IDs. Policy input is an explicit allowlist. Unknown fields and inconsistent reconciliation scope/not-applicable combinations are rejected. Evidence exports only the typed safe policy.

## Accounting-control boundaries

`AccountingPeriod.status` is the authoritative inclusive posting lock and `AccountingPeriod.ledger_activity_revision` is the authoritative activity sequence. `period_lock.py` acquires the SQLite tenant-period writer gate before period create/reopen overlap checks and before close or posting evaluates state. Direct and workflow posting both advance the revision in the journal transaction. `auto_process=true` keeps ingest and posting in one transaction.

A `READY_FOR_APPROVAL` period rejects direct and workflow posting with stable `ACCOUNTING_PERIOD_CLOSE_READY` `409`; an administrator must record a reasoned return-to-work. A closed period rejects with `ACCOUNTING_PERIOD_CLOSED`. Approved reconciliations and the latest variance run must match the current ledger revision. Each variance rerun creates its own fresh rows; only the latest run's rows can be updated or affect readiness. Historical rows/runs remain durable for audit.

Separation of duties is explicit: a journal requestor cannot approve their own request; a reconciliation preparer cannot provide final approval; final close/reopen/cancel/restart/return-to-work and policy overrides require an administrator. Ready freezes operational data and posting. Closed/cancelled cycles are service-level read-only. Create and reopen serialize the inclusive overlap decision before mutation.

## Evidence, input, output, and audit bounds

Central hard limits cover labels, names, notes, reasons, metadata, custom tasks, 500 reconciliations per cycle, 5,000 variance rows per run, approval comments, pagination, 20,000 evidence rows, and the 8 MiB evidence archive. Both reconciliation and variance limits use the central constants. Metadata uses the existing depth/key/node/string validator. Every close mutation stages a bounded semantic audit event under the trusted actor context; raw uploads, archive bytes, JWTs, passwords, credentials, environment state, stack traces, and unrestricted provider metadata are excluded.

The evidence service uses stable filenames and row order, canonical UTF-8 JSON, LF CSV, spreadsheet-safe text, normalized ZIP timestamps, and SHA-256 for every file. Exact cycle entity IDs scope audit references. Evidence rows and their own audit rows are outside an explicit snapshot cutoff, so generation does not create a manifest self-reference. Returned/downloaded bytes, persisted `CloseEvidence.manifest_sha256`, and the generation audit use the same manifest hash.

Draft persistence conditionally verifies and no-op locks the cycle status/content revision and period ledger revision at write time; a concurrent mutation produces a rollback conflict. Evidence is current only when both revisions match. Final close records evidence from the final `CLOSED` state in the same transaction.

## Failure, concurrency, and operational assumptions

- SQLModel `create_all` remains the repository's validated bootstrap; no unrelated migration platform was introduced.
- Unique/check/index constraints cover tenant labels, period date validity, one durable cycle per period, one reconciliation per account/cycle, one variance row per run/account/period, stable task keys, and one current approval per cycle/reference.
- Critical writes use conditional SQL `UPDATE ... WHERE version/content_revision/revision = expected` and require `rowcount == 1`; rollback removes failed audits and revision bumps.
- Separate-session/thread regressions prove overlapping period creation admits one writer, final close serializes against direct posting and workflow posting, and evidence persistence rejects a source changed between validation and its conditional lock.
- SQLite's single-writer gate is the validated close/post/period-overlap strategy. Multi-writer databases require database-native row locking or an equivalent gate before production use.
- Local loopback demonstration remains the validated deployment boundary. This review does not approve LAN/public hosting, regulatory use, or production financial close reliance.

## Browser acceptance at the corrected implementation

The flow under test was `http://127.0.0.1:8512/` → authenticated controlled preparer → **Close Workspace** → every workspace control tab and responsive layout. The API was loopback-only at `127.0.0.1:8012`, with a disposable seeded SQLite database. Browser path: Codex in-app Browser; no Playwright fallback.

| Check | Result | Evidence |
| --- | --- | --- |
| Page identity and meaningful render | PASS | Title `Modular Accounting Toolkit`; authenticated close workspace rendered March 2026 / March 2026 Close and readiness content; no framework overlay. |
| Control-by-control keyboard tabs | PASS | Arrow-key navigation selected `Overview`, `Reconciliations`, `Variance review`, `Journal approvals`, `Checklist`, and `Evidence & close`; each tab reported `aria-selected=true` and rendered its named panel. |
| 200% effective reflow | PASS | The 1280×720 desktop CSS viewport was halved to 640×360 to exercise the same two-times content/reflow constraint; measured `scrollWidth=640`, with no horizontal overflow or clipped top-level controls. The in-app Browser does not expose a literal page-zoom setting, so this is recorded as effective reflow evidence rather than a browser-chrome zoom claim. |
| 390 px viewport | PASS | Measured `innerWidth=390`, `scrollWidth=390`, `horizontalOverflow=false`; period/cycle selectors, workspace tabs, reconciliation heading, explanatory text, and account control remained readable and operable. |
| Console | PASS | Browser `error`/`warn` log query returned zero entries after login, all keyboard tab transitions, and both responsive checks. |
| Duplicate widget keys | PASS | No `DuplicateWidgetID`, `StreamlitDuplicateElementKey`, or duplicate-key warning in Streamlit runtime logs; the full Streamlit suite also passed. |
| Deprecated width API | PASS | No `use_container_width` occurrence under `src`; no deprecated-width warning in Streamlit runtime logs; `test_streamlit_source_contract.py` passed in the full suite. |

Desktop and 390 px screenshots were inspected during the Browser run. No horizontal scroll, overlapping controls, unreadable content, or relevant console error was observed. Destructive close/post/cancel buttons were not activated in browser acceptance; their behavior is covered by authenticated API/service and separate-session concurrency tests.

## Release security evidence

- The complete quality gate passed at the corrected implementation: 629 tests; 88.01% line coverage (9,070/10,306); 71.37% branch coverage (1,807/2,532); and all configured critical-module line/branch floors passed.
- The accounting-controls subset passed 52 tests. Ruff, format check, mypy, `pip check`, both dependency audits, and the current-tree secret scan passed; both dependency audits reported no known vulnerabilities.
- Gitleaks 8.30.1 scanned all refs with `gitleaks git --redact --no-banner --log-opts="--all"`: 277 commits, approximately 3.75 MB, no leaks.
- The deterministic route inventory is generated from implementation SHA `48e1d3aea6678aa49c8ba973a4d43a697de3e012` and maps 70 method/path entries with no unmapped application routes (62 application entries plus 8 documentation/schema entries).
- `macli health` returned overall `ok`; `inspect-extensions` loaded the three enabled extensions and `inspect-contracts` listed both published contracts. Scheduler/extension warnings in the one-shot health process were noncritical local-runtime state.
- GNU Make was not installed; the repository's stricter Python quality-gate runner executed the complete lint, format, typing, tests/coverage, dependency-audit, and secret-scan sequence directly.
- Docker was not installed in the Windows validation environment, so no local Compose runtime pass is claimed. Hosted container smoke validation remains required on the pushed exact head.
