# plugins/

Bundled reference plugins illustrating adapter contracts and operational extensions.

Each subdirectory exposes a `register` or provider factory entry point so the loader can discover and activate it at runtime:

- `analytics_baseline/` – Simple analytics probes for dashboards.
- `bank_plaid/` – Plaid-style bank feed demo provider for reconciliation plumbing.
- `fx_ecb/` – European Central Bank FX provider example.
- `fx_openexchangerates/` – Production-ready FX provider that requires an `OPENEXCHANGERATES_APP_ID`.
- `macro_fred/` – FRED-style macroeconomic series demo provider.
- `market_commodities/` – Synthetic commodity and futures price demo provider.
- `market_yfinance/` – Yahoo Finance market data adapter.
- `ops_heartbeat/` and `ops_resilience/` – Operational health reporters.
- `reference_cashflow/` – Demonstrates cashflow projections.
- `scenario_variance/` – Scenario orchestration helpers.
- `tax_oecd_vat/` – Illustrative OECD VAT rates provider.
- `tax_oecd_stub/` – OECD-style tax data reference package retained under its legacy implementation path.
- `tax_us_tables/` – Illustrative US federal/state tax table provider.

Use `python -m cli.macli scaffold-extension` to generate new plugins with tracing hooks and see [docs/guides/extension_guide.md](../../docs/guides/extension_guide.md).
