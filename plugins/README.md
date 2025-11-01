# plugins/

Bundled reference plugins illustrating adapter contracts and operational extensions.

Each subdirectory exposes a `register` function so the loader can discover and activate it at runtime:

- `analytics_baseline/` – Simple analytics probes for dashboards.
- `fx_ecb/` – European Central Bank FX provider example.
- `market_yfinance/` – Yahoo Finance market data adapter.
- `ops_heartbeat/` and `ops_resilience/` – Operational health reporters.
- `reference_cashflow/` – Demonstrates cashflow projections.
- `scenario_variance/` – Scenario orchestration helpers.
- `tax_oecd_stub/` – OECD-based tax data stub.

Use `python -m cli.macli scaffold-extension` to generate new plugins with tracing hooks and see [docs/guides/extension_guide.md](../docs/guides/extension_guide.md).
