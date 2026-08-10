# Roadmap

This roadmap reflects the repository state as of August 2026. Dates from the original modernization plan have been replaced with explicit status so completed foundations are not presented as overdue promises.

## Current Status

| Workstream | Status | Current state | Next meaningful step |
| --- | --- | --- | --- |
| Accounting-control demonstration | Complete for portfolio release | Snapshot orchestration, provenance, journal controls, CLI/API/Streamlit review surfaces, examples, and regression coverage are present. | Maintain release evidence and improve reviewer onboarding. |
| Adapter SDK foundation | Partial | Typed provider contracts, loader services, catalog metadata, caching behavior, bounded outbound-provider behavior, and reference adapters exist. | Package a documented third-party adapter SDK with conformance tests after the reliability tranche. |
| Provider marketplace | Planned | Provider discovery and metadata are represented in the internal catalog. No public marketplace or certification program exists. | Define package metadata, trust criteria, version compatibility, and review policy before implementation. |
| Workflow recipes | Foundation complete | Scenario plans, preview/inspection commands, sample workflows, orchestration helpers, and an accountant close walkthrough exist. | Add more accountant-oriented recipes only when they reuse validated service contracts and deterministic evidence. |
| Accountant close workspace | Complete for v0.2 Early Beta | Immutable lifecycle states, serialized SQLite period/posting/close gates, authoritative ledger-activity revisions, typed administrator policy exceptions, current variance runs, CAS revisions, bounded evidence, API routes, Streamlit workflow, and literal 200% browser acceptance are present. | Maintain the control boundary; evaluate database-native locks before any multi-writer deployment; do not expand the claim to ERP or production close certification. |
| Quality and forecast robustness | Active | Aggregate and first-wave critical-module coverage gates exist. Issue #59 now adds deterministic changed-production-line coverage, the remaining critical-module floors, and forecast finite-value/cadence/timezone hardening. | Complete the single reliability tranche on `quality/critical-coverage-and-forecast-robustness`. |
| Observability pack | Foundation complete | Metrics, tracing hooks, health/readiness endpoints, startup diagnostics, scheduler state, and CLI observability commands exist. | Add deployment examples, alerting guidance, and optional OTLP collector integration. |
| Container onboarding | Validated for local demonstration | Digest-pinned API and Streamlit images, hash-locked dependencies, Compose configuration, least-privilege checks, SBOMs, checksums, and trusted-event attestations are present. | Maintain pinned evidence and perform a separate review before broader deployment. |
| Public portfolio release | Public Early Beta | The repository is public with an explicit Early Beta / Portfolio Preview boundary and a completed post-UX code audit. | Maintain accurate release evidence; do not infer LAN or public-hosting approval from repository visibility. |

## Near-term Priorities

1. Complete issue #59: deterministic changed-production-line coverage, the remaining critical-module policy, and forecast robustness.
2. Keep setup instructions executable from a clean clone on Windows, macOS, Linux, and Docker.
3. Convert the current source-layout application into a conventionally installable Python project when packaging work begins.
4. Expand strict typing beyond the current targeted modules.
5. Persist provider-catalog administration rather than relying only on process configuration.
6. Handle Ruff 0.16 only through dedicated issue #102 after the reliability tranche.
7. Extend the validated v0.2 close controls only through explicit policy decisions and measured critical-module coverage.

## Future Opportunities

- Third-party adapter conformance kit and compatibility matrix.
- Signed or attestable provider metadata.
- Additional jurisdiction-aware tax demonstrations with explicit non-production disclaimers.
- Deployment examples for PostgreSQL, OTLP collectors, and Prometheus/Grafana.
- A production-grade web client only after the accounting-control workflows and API contracts stabilize.

Roadmap items are directional, not release commitments. Production financial, tax, treasury, and regulated-data use would require separate control design, security review, compliance assessment, and operational support.
