# Controlled accountant month-end close

This walkthrough uses synthetic March 2026 data. It is an Early Beta / Portfolio Preview demonstration, not an ERP-complete process, automatic bank reconciliation, production close certification, public-hosting approval, or regulatory compliance evidence. A passing rehearsal does not establish that a human accountant has evaluated the workflow.

## Run the isolated service rehearsal first

From a clean, verified repository worktree, use an environment satisfying the unchanged `requirements-dev.txt` and `requirements.txt`. The script bootstraps the application and SDK source roots itself; it does not install packages or modify an environment.

```powershell
python -m scripts.accountant_close_pilot --output .tmp/close-pilot-run
```

The output parent must already exist and the output directory must be new. Choose another new directory for a repeat run; never clean an existing directory to make the command pass. The command refuses dirty tracked/untracked source state, existing output, traversal and linked parents.

The command starts a child process with personal application/provider environment variables removed, environment-file loading disabled, an in-memory SQLite database, and Python socket connections denied. It does not start an HTTP listener, seed the default database, use live providers, or write a persistent database. This is process isolation for a trusted local rehearsal, not a sandbox for untrusted Python code.

The new directory retains:

- `close-pilot.json`: source HEAD/tree, checks, accounting expectations, blocker/state trace, and evidence digests; `acceptance_layer` is `services` and human/browser acceptance remains `NOT_RUN`.
- `close-final.zip`: actual recorded CLOSED evidence captured before the explicit reopen probe. The report explicitly records that it is historical, not current, after reopen.

The rehearsal starts blocked, records draft evidence, posts the staged adjustment, observes stale evidence, refreshes both affected reconciliations with independent approval, regenerates and reviews both material variance rows, attests local report freshness, reaches READY and CLOSED, verifies rejected direct posting leaves no partial transaction/journal/audit writes, and verifies explicit reopen permits posting while invalidating old evidence.

Separate runs have fresh operational timestamps and IDs. Identical accounting expectations and successful controls are repeatable; cross-run ZIP byte identity is not promised. Repeated retrieval of one unchanged recorded snapshot is checked byte-for-byte within a run.

## Seed a disposable database for the actual UI walkthrough

The service rehearsal above does not leave a database to open in Streamlit. For the UI, create a separate, explicitly named fresh database. **Configure the database before seeding or starting either service.** An API already running against another database will not switch when you change variables in a different shell.

Use the same verified repository root and compliant interpreter in both terminals. In the first terminal:

```powershell
$env:PYTHONPATH = "$PWD\src;$PWD\packages\provider-sdk\src;$PWD"
$env:MODACCT_ENV_FILE = ""
$env:MODACCT_DATABASE_URL = "sqlite:///./close-pilot-ui.db"
$env:DATABASE_URL = $env:MODACCT_DATABASE_URL
python -m scripts.seed_close_demo
```

The seed command requires an explicit `MODACCT_DATABASE_URL` naming a new local SQLite file, refuses an existing file or linked parent, and never deletes a database. Do not point it at a personal/customer database. If this name already exists, retain it and choose a new name. An application startup creates its configured database, so **seed before starting the API**.

The script prints the synthetic organization, cycle, budget, staged-workflow, account, user identifiers and the demo-only password. Keep the output local; do not copy authentication values into public test evidence. These accounts and the printed password are never for real data or a public/LAN service.

Then start the API in that configured terminal:

```powershell
python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

In a second terminal, select the same interpreter and root, repeat the environment configuration above **without rerunning the seed**, then:

```powershell
$env:API_BASE = "http://127.0.0.1:8000"
python -m streamlit run apps/web/app.py --server.address 127.0.0.1
```

Use unused loopback ports when necessary and set `API_BASE` to the actual API port. Do not terminate unrelated processes or expose either service beyond loopback.

## Independent accounting expectations

All amounts are USD. The displayed ledger balance uses **debits minus credits**; revenue is consequently negative. These fixed synthetic expectations are independent of the code calculating the report.

| Account | After the initial posted journals | After processing the staged adjustment |
| --- | ---: | ---: |
| 1000 — Operating cash | 380.00 | 355.00 |
| 4000 — Service revenue | -500.00 | -500.00 |
| 6000 — Payroll expense | 120.00 | 145.00 |
| Total | 0.00 | 0.00 |

The staged USD 25 entry debits payroll expense and credits cash. It is a **payroll settlement adjustment**, not an accrued-payable entry. Its historical source-reference identifier is retained for compatibility and does not define its accounting meaning.

The initial payroll control balance is deliberately wrong at 140.00. The correct post-adjustment control balances for the two existing reconciliations are **cash 355.00** and **payroll 145.00**, each with zero tolerance. Do not increase tolerance to suppress a blocker.

| Current variance row | Budget | Actual | Actual minus budget | Materiality |
| --- | ---: | ---: | ---: | --- |
| Revenue | -300.00 | -500.00 | -200.00 | Material under the absolute and percentage criteria |
| Payroll | 100.00 | 145.00 | 45.00 | Material under the 10% percentage criterion |

Materiality uses an absolute threshold of 100.00 **or** a percentage threshold of 0.10. Both rows require a reviewer disposition and note. The payroll row was already material at 120.00 before the adjustment; it was never an immaterial example under this policy.

The default journal-approval mode is `REQUESTED_ONLY`. The seeded revenue journal has a request and independent approval. This is not a claim that every posted journal is individually approved or that `ALL_PERIOD_TRANSACTIONS` policy is active.

## Complete the workflow in Streamlit

1. Sign in through **API Session** as `close-preparer@example.test`, use the printed organization ID, and select **March 2026** / **March 2026 Close** in **Close Workspace**. Record the actual readiness blockers and stable codes. They are expected at this stage.
2. In **Evidence & close**, generate and download draft evidence. Retain its manifest locally. A download must retrieve a recorded snapshot; it must not silently create one.
3. Use **Process next staged journal** to process the printed adjustment. The open period accepts it. Cash must now be 355.00 and payroll 145.00. The ledger revision advances: the earlier reconciliation approvals, variance run and draft evidence are no longer current. A request for that stale recorded download must be rejected rather than silently regenerated.
4. In **Reconciliations**, refresh **both** existing account records against the current ledger revision, not just payroll: cash control balance 355.00 and payroll control balance 145.00; zero tolerance; notes describing the synthetic support. Save each using its current version. Re-preparation clears prior approvals. Confirm the preparer cannot self-approve.
5. Log out and sign in as `close-reviewer@example.test`. Independently approve both refreshed reconciliations. Return to the preparer as needed for report generation; do not share a signed-in browser session as evidence of two actors.
6. Generate a **new current variance run after the staged posting**, using the printed budget, horizon 30, absolute threshold 100.00, percentage threshold 0.10 and refresh. Do not merely edit the stale run. As the reviewer, mark both current material rows **EXPLAINED**, supplying a nonempty note for each. These dispositions document synthetic differences; they do not post another journal or change the budget.
7. In **Journal approvals**, inspect the seeded revenue request and its append-only decision history. The preparer requested and the reviewer approved; audit actor attribution must agree. Leave `REQUESTED_ONLY` unchanged.
8. As the preparer, complete the **Provider and report freshness reviewed** attestation with a note stating that the controlled local source and refreshed report were inspected. System-derived tasks must not be manually overridden. Readiness must have no substantive blockers; use the server-provided next actions for any unexpected blocker, and record the gap rather than weakening policy.
9. Mark **Ready for approval** using the current cycle version. READY freezes close controls and direct/workflow posting. The in-period direct posting probe must return `409` / `ACCOUNTING_PERIOD_CLOSE_READY` with no persisted journal. Generate a fresh recorded READY evidence bundle where required; this is draft evidence, not final approval.
10. Log out and sign in as `close-admin@example.test`. Close the cycle. The service recalculates readiness and atomically closes the cycle and period while generating current final evidence from `CLOSED`. The final approval checklist item and `approved_at` are set here, not earlier.
11. Download and retain the recorded **final** ZIP and manifest. Repeat the unchanged download and verify the bytes/digests match. Use the posting-lock form with cash/revenue account IDs and a March date: require `409` / `ACCOUNTING_PERIOD_CLOSED`, without partial journal/audit writes.
12. Explicitly reopen with a nonempty review reason. The prior final bundle remains useful historical evidence, but is now stale and cannot be presented as current. Ordinary posting is again permitted. Stop here; do not silently create another final close or overwrite the retained final bundle.

UI, API and service-layer acceptance are distinct. Record the actual browser/viewport, role switches, observed controls and any sanitized failure in the [reviewer worksheet](accountant_close_pilot_review.md). A completed automated rehearsal must not fill in human observations automatically.

## Evidence contents and boundaries

Generate evidence with the existing POST before downloading. The POST builds one source snapshot and shares its manifest across the response, durable row and audit. Download returns `409 CLOSE_EVIDENCE_NOT_CURRENT` when evidence is missing, stale after a close/ledger mutation, reopened with the wrong final/draft classification, or fails the durable-hash comparison. GET never persists or silently regenerates evidence.

The ZIP contains `manifest.json`, `close-cycle.json`, `readiness.json`, `trial-balance.csv`, `reconciliations.csv`, `reconciliation-exceptions.csv`, `variance-reviews.csv`, `variance-review-runs.csv`, `journal-approvals.csv`, `journal-approval-decisions.csv`, `checklist.csv`, `audit-references.csv`, and `provenance.json`. Audit references are bounded to the selected period/cycle and its exact reference IDs. Current variance rows and durable run history remain separate. Files use deterministic ordering, canonical JSON, LF line endings, normalized ZIP timestamps and spreadsheet-safe text.

## Reproducible regression commands

```powershell
python -m pytest -q tests/test_accountant_close_pilot.py tests/test_close_pilot_seed.py tests/test_close_demo.py
python -m pytest -q tests/test_close_readiness.py tests/test_period_posting_lock.py tests/test_close_evidence.py tests/test_close_integrity_regressions.py
python -m pytest -q tests/test_close_api.py tests/test_close_tenant_isolation.py
```

The focused pilot regression exercises the documented seed without disabling variance review or other required controls. The broader existing suites additionally cover authenticated/tenant boundaries, both direct and staged posting paths, concurrency ordering, stale-version rejection, bounded evidence and rollback semantics. Preserve those gates; no new dependency, live-provider prerequisite or production-deployment permission is introduced by this pilot.
