# Steward's Report

## Metrics Overview
| Metric | Measurement | Notes |
| --- | --- | --- |
| Test coverage (apps/cli/plugins) | 52.55% (6,974/13,272 lines executed) | Approximated with `python -m trace` because `pytest-cov` is unavailable in the sandbox. 【0a7457†L1-L41】 |
| Average cyclomatic complexity | Snapshot service 3.15; plugin loader 2.89; snapshot router 1.00; CLI 6.86; snapshot application 4.83 | Complexity computed via custom AST walker across core modules. 【05e183†L1-L38】 |
| Internal cohesion ratio | Snapshot service 0.33; plugin loader 0.00; snapshot router 0.00; CLI 0.53 | Ratio = internal imports / total imports, highlighting external dependencies. 【861526†L1-L24】 |
| Test runtime | 9.64s (`pytest`) | Baseline validation without trace instrumentation. 【42f66f†L1-L16】 |
| Trace-instrumented runtime | 53.56s (`python -m trace --module pytest`) | Heavyweight coverage sampling for audit snapshots. 【d537dd†L1-L15】 |
| Code footprint | apps 1016 KB, cli 96 KB, plugins 100 KB | Measured via `du -sh` for core packages. 【a89065†L1-L4】 |

## Key Findings & Recommendations
- The CLI remains the most complex surface (avg. complexity 6.86); continue extracting shared helpers and consider subcommands per provider to further lower branching. 【05e183†L24-L37】
- Snapshot HTTP and CLI routes are now explicitly tagged (`# agent-entrypoint`) to guide automation; future observability work should attach structured metrics to these entry points. 【F:apps/api/routers/snapshot.py†L13-L33】【F:cli/macli.py†L218-L298】
- Coverage is uneven (CLI coverage 35.38% vs apps 73.80%); prioritize focused CLI tests around provider validation and CSV ingestion to close the gap. 【0a7457†L1-L41】
- Plugin loader cohesion is low (0.00 ratio) by design; document extension guidelines stressing the pure boundary to keep provider loading decoupled. 【861526†L1-L24】

## Simplification Log
- Consolidated provider-backed CLI commands through `_execute_provider_command`, removing duplicated session/actor orchestration and enabling safer automation hooks. 【F:cli/macli.py†L38-L137】
- Simplified `SnapshotResult.as_payload` to build the response dictionary in a single expression, reducing mutation and clarifying payload composition. 【F:apps/api/services/snapshot_service.py†L173-L204】
- Added runtime provider validation via `_resolve_provider_key`, surfacing actionable `click.BadParameter` errors when operators pass unknown provider keys. 【F:cli/macli.py†L38-L111】
- Documented dynamic provider defaults in the README so operators understand implicit selection rules before automation extends these commands. 【F:README.md†L28-L35】

## Knowledge & Automation Handover
- `cli.macli` commands now expose `# agent-safe-task` and `# agent-entrypoint` annotations to signal automation-safe orchestration layers for scheduled sync jobs and snapshot generation. 【F:cli/macli.py†L38-L137】【F:cli/macli.py†L218-L298】
- HTTP snapshot retrieval is tagged for agents, and automation guidance remains centralized in `AUTOMATION.md`; agents should respect Makefile targets for validation. 【F:apps/api/routers/snapshot.py†L13-L33】【F:AUTOMATION.md†L1-L52】
- Trace-based coverage scripts (see Metrics) can be rerun ad-hoc without additional dependencies, offering a lightweight alternative when package installation is restricted. 【0a7457†L1-L41】

## Future Roadmap
### Short Term (next sprint)
- Expand CLI test coverage to exercise provider validation, CSV ingestion edge cases, and snapshot table rendering for regression protection. 【0a7457†L1-L41】
- Capture structured metrics (cache hits/misses, provider latency) directly from CLI and HTTP entry points to feed observability dashboards.
- Author provider onboarding docs emphasising plugin metadata expectations to improve cohesion and reduce runtime surprises.

### Mid Term (1–2 quarters)
- Introduce async provider execution with concurrency limits to reduce snapshot latency while preserving determinism.
- Add contract tests for extension providers to enforce capability declarations and error handling across plugin ecosystems.
- Wire automated coverage collection into CI using `python -m trace` fallback so audits always surface measurable coverage even when plugins are unavailable.

### Long Term (2+ quarters)
- Containerize CLI + API flows with baked-in observability (OpenTelemetry, metrics exporters) for reproducible deployments.
- Explore agent-driven scheduling that watches provider freshness and triggers `macli` commands via the annotated `# agent-*` hooks.
- Establish dependency freshness automation (e.g., Renovate rules tuned for provider adapters) to guard against sprawl without manual oversight.
