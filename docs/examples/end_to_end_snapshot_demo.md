# End-to-End Snapshot and Control Demonstration

This demonstration links provider inputs, snapshot generation, accounting-control checks, provenance output, and health/readiness verification in one auditable flow.

## Purpose

Show that the toolkit can:

- ingest provider-backed financial inputs (FX, commodity, tax)
- produce a consolidated snapshot
- preserve provenance and diagnostics
- support downstream journal-control validation
- expose operational health/readiness signals

## Controlled Inputs

- Base currency: USD
- Commodity symbols: XAU, XAG
- Jurisdiction scope: US
- Example providers: `fx_openexchangerates`, `market_commodities`, `tax_us_tables`

## Step 1: Generate Snapshot With Providers

```bash
python -m cli.macli snapshot --base USD --commodity XAU --commodity XAG --jurisdiction US --format json
```

Expected evidence in payload:

- `providers.fx`, `providers.commodity`, `providers.tax`
- `diagnostics` including missing/stale-section indicators
- consolidated `fx_rates`, `commodity_quotes`, and `tax_rules`
- cache metrics (`hits`, `misses`, `size`) for repeatability analysis

## Step 2: Validate Journal Control Behavior

```bash
python -m pytest -q tests/test_modular_accounting_controls.py tests/test_ledger_service.py
```

Expected controls:

- balanced posting acceptance and unbalanced posting rejection
- account traceability for posted transactions
- reversal and settlement-style balancing behavior where covered

## Step 3: Verify Provenance and FX Accounting Narrative

- Review the foreign-currency case study: [foreign_currency_accounting_case_study.md](foreign_currency_accounting_case_study.md)
- Confirm provider/rate provenance table and balanced journal snapshots are present

## Step 4: Confirm API Health and Readiness

```bash
python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/ready
```

Expected result:

- health endpoint returns service status payload
- readiness endpoint reports startup/extension state for operational gating

## Visual Evidence

- Architecture: [architecture-overview.svg](assets/architecture-overview.svg)
- CLI snapshot: [cli-snapshot-consolidated.svg](assets/cli-snapshot-consolidated.svg)
- API health snapshot: [api-health-snapshot.svg](assets/api-health-snapshot.svg)
- Foreign-currency journal evidence: [fx-case-study-terminal.svg](assets/fx-case-study-terminal.svg), [fx-case-study-journal.svg](assets/fx-case-study-journal.svg)

## Scope Guardrails

This is a toolkit demonstration, not a full ERP deployment. It intentionally excludes payroll, AP/AR subledger automation, full tax-engine compliance automation, treasury execution, and production React UI scope.
