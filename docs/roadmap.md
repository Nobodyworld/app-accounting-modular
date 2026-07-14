# Roadmap

This roadmap reflects the repository state as of July 2026. Dates from the original modernization plan have been replaced with explicit status so completed foundations are not presented as overdue promises.

## Current Status

| Workstream | Status | Current state | Next meaningful step |
| --- | --- | --- | --- |
| Accounting-control demonstration | Complete for portfolio release | Snapshot orchestration, provenance, journal controls, CLI/API/Streamlit review surfaces, examples, and regression coverage are present. | Maintain release evidence and improve reviewer onboarding. |
| Adapter SDK foundation | Partial | Typed provider contracts, loader services, catalog metadata, caching behavior, and reference adapters exist. | Package a documented third-party adapter SDK with conformance tests. |
| Provider marketplace | Planned | Provider discovery and metadata are represented in the internal catalog. No public marketplace or certification program exists. | Define package metadata, trust criteria, version compatibility, and review policy before implementation. |
| Workflow recipes | Foundation complete | Scenario plans, preview/inspection commands, sample workflows, and orchestration helpers exist. | Add accountant-oriented reconciliation and close-control recipes with expected journal evidence. |
| Observability pack | Foundation complete | Metrics, tracing hooks, health/readiness endpoints, startup diagnostics, scheduler state, and CLI observability commands exist. | Add deployment examples, alerting guidance, and optional OTLP collector integration. |
| Container onboarding | In validation | API and Streamlit Dockerfiles plus Compose configuration exist. | Keep container build and startup smoke coverage in CI. |
| Public portfolio release | In owner review | README, screenshots, architecture diagrams, case studies, security policy, license, contribution docs, and release audit are present. | Complete hosted CI and repository-setting review before changing visibility. |

## Near-term Priorities

1. Keep setup instructions executable from a clean clone on Windows, macOS, Linux, and Docker.
2. Convert the current source-layout application into a conventionally installable Python project when packaging work begins.
3. Expand strict typing beyond the current targeted modules.
4. Replace remaining Streamlit deprecated parameters and reduce UI maintenance warnings.
5. Persist provider-catalog administration rather than relying only on process configuration.
6. Add accountant-centered workflow recipes for reconciliation, period close, variance review, and journal approval evidence.

## Future Opportunities

- Third-party adapter conformance kit and compatibility matrix.
- Signed or attestable provider metadata.
- Additional jurisdiction-aware tax demonstrations with explicit non-production disclaimers.
- Deployment examples for PostgreSQL, OTLP collectors, and Prometheus/Grafana.
- A production-grade web client only after the accounting-control workflows and API contracts stabilize.

Roadmap items are directional, not release commitments. Production financial, tax, treasury, and regulated-data use would require separate control design, security review, compliance assessment, and operational support.
