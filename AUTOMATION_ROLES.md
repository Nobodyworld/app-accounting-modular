# Automation Roles

## Snapshot Steward Agent
- **Trigger**: Cron or event-driven job needing a unified FX/commodity/tax snapshot.
- **Entry points**: `cli.macli snapshot` (`# agent-entrypoint`) and `/snapshot` router for HTTP orchestration.
- **Checklist**:
  1. Ensure providers are configured (check `available_providers`).
  2. Execute `python -m cli.macli snapshot --format json` to capture machine-readable payloads.
  3. Emit cache metrics to monitoring by parsing the `cache_stats` section of the response.
- **Fallback**: On provider failure, rerun with `--fx-provider`, `--commodity-provider`, or `--tax-provider` overrides for targeted retries. 【F:cli/macli.py†L218-L298】【F:apps/api/routers/snapshot.py†L13-L33】

## Provider Sync Operator
- **Trigger**: Scheduled data refresh for FX rates or commodity prices.
- **Entry points**: `cli.macli sync-fx` and `cli.macli sync-prices`, marked as `# agent-safe-task`.
- **Checklist**:
  1. Validate provider keys with `_resolve_provider_key`; the CLI raises actionable errors if the key is unknown.
  2. Run `python -m cli.macli sync-fx --base USD` (or `sync-prices`) and capture CLI logs for audit trails.
  3. Monitor the returned count to confirm volume synced; escalate if zero to investigate upstream provider health.
- **Fallback**: On repeated failures, disable the provider in configuration and notify the Snapshot Steward Agent. 【F:cli/macli.py†L38-L137】

## Coverage Auditor Agent
- **Trigger**: Release readiness checks or periodic quality reviews.
- **Entry points**: Trace-based coverage workflow using the sandbox-friendly `python -m trace` command.
- **Checklist**:
  1. Run `python -m trace --count --coverdir tracecov --module pytest`.
  2. Use the provided parsing script (see Steward's Report) to compute aggregate coverage percentages.
  3. Attach the resulting metrics to `REPORTS/` or release notes as needed.
- **Fallback**: If trace output is noisy, prune standard-library `.cover` files before archiving to focus on project modules. 【0a7457†L1-L41】
