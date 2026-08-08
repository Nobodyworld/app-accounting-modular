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
9. When readiness has no blockers, mark the cycle **Ready for approval**. Then generate evidence so its source version includes the ready state. Download the deterministic ZIP and retain the displayed manifest SHA-256.
10. Log out and sign in as `close-admin@example.test`. Close the accounting period. Final close recalculates readiness and atomically closes the cycle and period.
11. In **Evidence & close**, use the posting-lock verification form with the printed cash and revenue account IDs and a March 2026 date. The API must return `409` with `ACCOUNTING_PERIOD_CLOSED`, and no journal or audit mutation remains.
12. Enter a nonempty reason and explicitly reopen the period. Prior evidence becomes stale and ordinary posting is permitted again.

## Evidence contents

The ZIP contains `manifest.json`, `close-cycle.json`, `readiness.json`, `trial-balance.csv`, `reconciliations.csv`, `reconciliation-exceptions.csv`, `variance-reviews.csv`, `journal-approvals.csv`, `checklist.csv`, `audit-references.csv`, and `provenance.json`. Files have deterministic ordering, canonical JSON, LF line endings, normalized ZIP timestamps, and spreadsheet-safe text.

## Reproducible control tests

```powershell
pytest -q tests/test_close_readiness.py tests/test_period_posting_lock.py tests/test_close_evidence.py
```

These tests prove the legal/illegal lifecycle, two-person controls, inclusive direct/workflow posting lock, no partial writes, evidence determinism, final close, rejection after close, and explicit reopen.
