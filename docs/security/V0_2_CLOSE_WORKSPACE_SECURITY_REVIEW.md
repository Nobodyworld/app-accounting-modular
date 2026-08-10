# v0.2 Accountant Close Workspace security review

## Scope and exact correction

- Current main baseline: `445241b4514baa42feef0541b677233920540114`.
- Final-integration starting product head: `a08dcb96abbdb99bfee0f7bd3fb0bd6c30551e30`.
- Validated merged implementation head before this documentation refresh: `ba2af5ca17bb71e0888f0eb3dd0ebebc31a6d4f2`.
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

Central hard limits cover labels, names, notes, reasons, metadata, custom tasks, 500 reconciliations per cycle, 5,000 variance rows per run, 500 approvals per cycle, approval comments, 100-record default/500-record maximum list pages, 20,000 evidence rows, and the 8 MiB evidence archive. Reconciliation, current-variance, approval-summary, and approval-decision reads are independently paged. Metadata uses the existing depth/key/node/string validator. Every close mutation stages a bounded semantic audit event under the trusted actor context; raw uploads, archive bytes, JWTs, passwords, credentials, environment state, stack traces, and unrestricted provider metadata are excluded.

The evidence service uses stable filenames and row order, canonical UTF-8 JSON, LF CSV, spreadsheet-safe text, normalized ZIP timestamps, and SHA-256 for every file. Exact cycle entity IDs scope audit references. Evidence rows and their own audit rows are outside an explicit snapshot cutoff, so generation does not create a manifest self-reference. Account enrichment queries only sorted, deduplicated reconciliation account IDs and shares the archive row budget. POST builds once; its returned manifest, persisted `CloseEvidence.manifest_sha256`, and generation audit use the same snapshot and hash.

Draft persistence conditionally verifies and no-op locks the cycle status/content revision and period ledger revision at write time; a concurrent mutation produces a rollback conflict. Download requires the latest tenant record to match cycle revision, ledger revision, and current draft/final classification, then requires a deterministic rebuild to match its durable hash. Missing, stale, reclassified, or mismatched evidence returns `409 CLOSE_EVIDENCE_NOT_CURRENT`; GET creates no evidence or audit row. Final close records evidence from the final `CLOSED` state in the same transaction.

## Failure, concurrency, and operational assumptions

- SQLModel `create_all` remains the repository's validated bootstrap; no unrelated migration platform was introduced.
- Unique/check/index constraints cover tenant labels, period date validity, one durable cycle per period, one reconciliation per account/cycle, one variance row per run/account/period, stable task keys, and one current approval per cycle/reference.
- Critical writes use conditional SQL `UPDATE ... WHERE version/content_revision/revision = expected` and require `rowcount == 1`; rollback removes failed audits and revision bumps.
- Separate-session/thread regressions prove overlapping period creation admits one writer, evidence persistence rejects a source changed between validation and its conditional lock, and event-controlled write-gate ownership covers both outcomes for direct and workflow posting. Close-first closes atomically and rejects posting without a journal or revision change. Posting-first commits one complete journal and one revision, makes prior source-bound evidence/reconciliation/variance state stale, and leaves final close rejected with the period open.
- SQLite's single-writer gate is the validated close/post/period-overlap strategy. Multi-writer databases require database-native row locking or an equivalent gate before production use.
- Local loopback demonstration remains the validated deployment boundary. This review does not approve LAN/public hosting, regulatory use, or production financial close reliance.

## Browser acceptance

The earlier supporting flow was `http://127.0.0.1:8512/` → authenticated controlled preparer → **Close Workspace** → every workspace control tab and responsive layout. The API was loopback-only at `127.0.0.1:8012`, with a disposable seeded SQLite database. That run used the Codex in-app Browser and remains supporting reflow evidence, not literal Microsoft Edge zoom evidence.

| Check | Result | Evidence |
| --- | --- | --- |
| Page identity and meaningful render | PASS | Title `Modular Accounting Toolkit`; authenticated close workspace rendered March 2026 / March 2026 Close and readiness content; no framework overlay. |
| Control-by-control keyboard tabs | PASS | Arrow-key navigation selected `Overview`, `Reconciliations`, `Variance review`, `Journal approvals`, `Checklist`, and `Evidence & close`; each tab reported `aria-selected=true` and rendered its named panel. |
| Literal Edge 200% zoom | PASS | The owner set the verified dedicated Edge tab through Edge menu (…) → Zoom → 200%. The unchanged `1078×1870` outer window changed from device-pixel ratio 1 and a `788×1828` CSS viewport to device-pixel ratio 2 and a `394×890` CSS viewport, independently confirming the literal zoom. All six close sections passed. |
| 390 px viewport | PASS | At device-pixel ratio 2, the exact `390×844` CSS viewport measured `innerWidth=390`, `innerHeight=844`, and `scrollWidth=390`; all six sections rendered without page-level horizontal overflow. |
| Console | PASS | Application-origin browser logs contained no feature error or warning after login, all six literal-zoom sections, mutation confirmation, keyboard traversal, and the responsive recheck. One Microsoft Edge extension-only WebSocket error from `chrome-extension://gpphkfbcpidddadnkolkpfckpihlkkil/` was excluded as unrelated to the loopback application. |
| Duplicate widget keys | PASS | No `DuplicateWidgetID`, `StreamlitDuplicateElementKey`, or duplicate-key warning in Streamlit runtime logs; the full Streamlit suite also passed. |
| Deprecated width API | PASS | No `use_container_width` occurrence under `src`; no deprecated-width warning in Streamlit runtime logs; `test_streamlit_source_contract.py` passed in the full suite. |

The literal acceptance used Microsoft Edge `151.0.4129.72` on Windows 25H2 build `26200.8894` (64-bit), a freshly authenticated loopback session, controlled sample data, and a nonproduction JWT secret. At 200%, `Overview`, `Reconciliations`, `Variance review`, `Journal approvals`, `Checklist`, and `Evidence & close` each rendered without page-level horizontal overflow or inaccessible visible mutation controls. Financial values remained legible; long-value metrics collapsed to one per row; table surfaces retained deliberate internal horizontal scrolling; textual status, blockers, warnings, and errors remained visible; expanders remained operable; and evidence generation exposed the recorded manifest plus a reachable ZIP download. The generated draft manifest was `653ca13baef87c308f4ad1befec20f4d157b1a08af94045585741bb67ec2c1a6`.

Keyboard acceptance at literal 200% passed: `Tab` reached the rendered inputs, buttons, downloads, expanders, and table controls in every section; `Shift+Tab` reversed direction; visible focus remained present; arrow keys selected all six close tabs in order; and no keyboard trap occurred. The exact `390×844` CSS viewport recheck also passed with `innerWidth=390`, `scrollWidth=390`, clean forward/reverse focus, and clean arrow-key navigation. No duplicate-widget-key warning, deprecated Streamlit width warning, raw API exception, credential, JWT, refresh token, or authorization header appeared. The task-only services, database, and logs were removed after validation. Destructive close/post/cancel actions were not activated in browser acceptance; their behavior remains covered by authenticated API/service and separate-session concurrency tests.

## Release security evidence

- The complete pytest suite passed 639 tests. Release-authoritative line coverage is 87.99% (9,121/10,366); branch evidence is 71.45% (1,829/2,560). All nine configured critical-module line/branch floors passed.
- The accounting-controls subset passed 52 tests. Ruff, format check, mypy, `pip check`, the development dependency audit, and the current-tree secret scan passed.
- The runtime lock matches `origin/main` byte-for-byte, pins GitPython 3.1.58, verifies at SHA-256 `13c6b89298fd1767aa6f4a44b26e7cffcb6a7a0f146fa8e8ea80e2ac978c1312`, and its required hashed audit reports no known vulnerabilities. The aggregate quality gate passes with no skipped tool.
- Gitleaks scanned all refs with `gitleaks git . --log-opts="--all" --redact`: 285 commits, approximately 3.83 MB, no leaks.
- The deterministic route inventory maps 71 method/path entries with no unmapped application routes (63 application entries plus 8 documentation/schema entries).
- `macli health` returned overall `ok`; `inspect-extensions` loaded the three enabled extensions and `inspect-contracts` listed both published contracts. Scheduler/extension warnings in the one-shot health process were noncritical local-runtime state.
- GNU Make was not installed; the repository's stricter Python quality-gate runner executed the complete lint, format, typing, tests/coverage, dependency-audit, and secret-scan sequence directly.
- Docker is not installed in the Windows validation environment, so no local Compose runtime pass is claimed. Hosted container supply-chain and required smoke validation remain required on the pushed exact head.

| Critical module | Lines | Branches |
| --- | ---: | ---: |
| `services/ledger_service.py` | 93.14% | 87.10% |
| `services/workflow_service.py` | 84.53% | 68.18% |
| `security.py` | 87.41% | 85.71% |
| `services/auth_session_service.py` | 89.57% | 73.08% |
| `services/period_lock.py` | 96.43% | 92.86% |
| `services/close_service.py` | 91.65% | 82.39% |
| `services/reconciliation_service.py` | 91.94% | 81.37% |
| `services/close_evidence_service.py` | 95.16% | 81.25% |
| `routers/close.py` | 93.68% | 78.12% |
