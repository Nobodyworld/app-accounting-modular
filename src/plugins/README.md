# plugins/

Bundled reference plugins illustrating adapter contracts and operational extensions.

Each subdirectory exposes a `register` function so the loader can discover and activate it at runtime:

- `analytics_baseline/` – Simple analytics probes for dashboards.
- `bank_plaid/` – Plaid-style bank feed stub for reconciliation plumbing.
- `fx_ecb/` – European Central Bank FX provider example.
- `fx_openexchangerates/` – Production-ready FX provider that requires an `OPENEXCHANGERATES_APP_ID`.
- `macro_fred/` – FRED-style macroeconomic series stub.
- `market_commodities/` – Commodity and futures price stub provider.
- `market_yfinance/` – Yahoo Finance market data adapter.
- `ops_heartbeat/` and `ops_resilience/` – Operational health reporters.
- `reference_cashflow/` – Demonstrates cashflow projections.
- `scenario_variance/` – Scenario orchestration helpers.
- `tax_oecd_vat/` – OECD VAT rates stub.
- `tax_oecd_stub/` – OECD-based tax data stub.
- `tax_us_tables/` – US federal/state tax table stub.

Use `python -m cli.macli scaffold-extension` to generate new plugins with tracing hooks and see [docs/guides/extension_guide.md](../../docs/guides/extension_guide.md).
