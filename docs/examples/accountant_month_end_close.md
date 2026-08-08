# Controlled accountant month-end close

This walkthrough exercises the v0.2 close cycle with controlled sample data. It is an Early Beta / Portfolio Preview demonstration, not an ERP-complete process, automatic bank reconciliation, production close certification, public-hosting approval, or regulatory compliance evidence.

## Seed the controlled example

Use a fresh local database, start the API and Streamlit as described in the README, then run:

```powershell
$env:PYTHONPATH = "$PWD\src;$PWD"
$env:MODACCT_DATABASE_URL = "sqlite:///./close-demo.db"
python scripts/seed_close_demo.py
```

The command creates one organization, a preparer, an independent reviewer, an administrator, a March 2026 period, balanced posted journals, one unposted staged adjustment, a matched/approved cash reconciliation, a documented payroll exception, material and immaterial budget variances, an independently approved posted journal, and the deterministic eight-control checklist. It prints every identifier needed by the UI. All three controlled users use the printed demo password; never reuse it outside the disposable demo database.

## Complete the workflow in Streamlit

1. Sign in as `close-preparer@example.test`, enter the printed organization ID, and open **Close Workspace**.
2. Select **March 2026** and **March 2026 Close**. Review the API-derived blockers and stable codes.
3. Use **Process next staged journal** to send the referenced item through the existing staged workflow service. The period is still open, so the balanced item posts normally.
4. In **Reconciliations**, update the payroll account using the printed account ID and the corrected control balance. The displayed ledger ending balance is server-derived; `difference = control balance - ledger ending balance`.
5. Log out and sign in as `close-reviewer@example.test`. Approve the corrected reconciliation. Self-approval remains blocked.
6. In **Variance review**, filter material rows, select the unresolved revenue variance, record a disposition, and add the required reviewer note. The row came from the existing BudgetService report and retains its budget, horizon, plan, revision, currency, and generation provenance.
7. Review the already approved posted-journal request and its append-only decision history. A requestor cannot approve their own request.
8. In **Checklist**, complete the provider/report freshness attestation. System-derived tasks cannot be manually overridden.
9. When readiness has no blockers, mark the cycle **Ready for approval**. Ready freezes close controls and both direct/workflow posting. An in-period attempt returns `409` with `ACCOUNTING_PERIOD_CLOSE_READY`; an administrator must return the cycle to work with a reason before posting. A later successful post advances the period ledger revision, making the prior reconciliation, variance run, and evidence stale until refreshed.
10. Log out and sign in as `close-admin@example.test`. Close the accounting period. Final close recalculates readiness and atomically closes the cycle and period while generating current final evidence from the `CLOSED` state. `approved_at` and the final checklist task are set only here.
11. In **Evidence & close**, use the posting-lock verification form with the printed cash and revenue account IDs and a March 2026 date. The API must return `409` with `ACCOUNTING_PERIOD_CLOSED`, and no journal or audit mutation remains.
12. Enter a nonempty reason and explicitly reopen the period. Reopen is rejected if another same-tenant open period overlaps any inclusive boundary. Prior evidence becomes stale and ordinary posting is permitted again. A cancelled cycle remains durable and read-only until an administrator restarts it with a reason.

## Evidence contents

The ZIP contains `manifest.json`, `close-cycle.json`, `readiness.json`, `trial-balance.csv`, `reconciliations.csv`, `reconciliation-exceptions.csv`, `variance-reviews.csv`, `variance-review-runs.csv`, `journal-approvals.csv`, `journal-approval-decisions.csv`, `checklist.csv`, `audit-references.csv`, and `provenance.json`. Audit references are limited to the selected period/cycle and its exact child/reference IDs, with evidence records and their own audit rows outside the explicit snapshot cutoff. Only the latest variance run's current rows appear in `variance-reviews.csv`; durable run history remains in `variance-review-runs.csv`. Every exported row type counts toward the cap. Files have deterministic ordering, canonical JSON, LF line endings, normalized ZIP timestamps, spreadsheet-safe text, and one manifest hash shared by returned/downloaded bytes, persisted metadata, and the generation audit.

## Reproducible control tests

```powershell
pytest -q tests/test_close_readiness.py tests/test_period_posting_lock.py tests/test_close_evidence.py tests/test_close_integrity_regressions.py
```

These tests prove the legal/illegal lifecycle, two-person controls, inclusive direct/workflow READY and CLOSED posting locks, separate-session close/post and overlap races, ledger-revision staleness, no partial writes, conditional evidence persistence, manifest equality, final close, and explicit reopen.
