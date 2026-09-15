# Repository Specification

- **Repository**: `app-accounting-modular`
- **Status**: public **Early Beta / Portfolio Preview**
- **Last Updated**: 2026-09-13
- **Current product baseline**: `main` after merged PR #158

## Purpose

`app-accounting-modular` is a modular accounting-control toolkit for demonstrating auditable close, journal, provider, forecasting, provenance, and review workflows without claiming ERP completeness or production financial certification.

The validated product boundary is a local/loopback portfolio demonstration. Production tax, treasury, bank-feed, multi-writer accounting, provider-marketplace, public/LAN hosting, regulated-data, or commercial-support claims require separate design and validation.

## Stack overview

| Layer | Details |
| --- | --- |
| Runtime | Python 3.12+; hosted quality matrix covers 3.12, 3.13, and 3.14 |
| Frameworks | FastAPI, SQLModel, Streamlit |
| Provider authoring | standalone `modular-accounting-provider-sdk` v0.5 author kit under `packages/provider-sdk/` |
| Tooling | Ruff, pytest/coverage, configured mypy, pip-audit, repository quality/security tooling |
| CI | GitHub Actions with required Python matrix, container smoke, changed-production coverage, and container supply-chain checks |
| Merge policy | protected `main`, pull-request-only squash merging, linear history, resolved review threads, strict required checks |

## Implemented product contracts

- **Accounting controls / Close Workspace**: persistent accounting periods and close cycles, serialized posting gates, reconciliations, variance review, independent approvals, checklist/readiness, deterministic evidence, explicit lifecycle transitions, and server-authoritative Streamlit workflows.
- **Provider SDK v0.3**: immutable manifests, structural contracts, deterministic conformance, compatibility checks, allowlist-enforced loading, scaffolding, and CLI evidence.
- **Provider governance v0.4**: persistent safe registration evidence, organization enablement/default policy, revision-protected audit mutation, deterministic resolution, API/Streamlit administration, and secret-free evidence.
- **Provider Author Kit v0.5**: standalone SDK package, authoritative in-tree PEP 517 backend, typed scaffold/validate/build tooling, deterministic wheel/sdist evidence, clean-environment acceptance, and compatibility facade.
- **Close pilot / UX**: repeatable synthetic accountant rehearsal and walkthrough plus Windows/actual-browser acceptance; PR #158 completed immediate refresh, denial feedback, and active-tab stability.

## Provider trust boundary

`settings.allowed_providers` is the sole executable provider trust source. Persistence may retain evidence and organization policy and may narrow execution, but it may never broaden trust or authorize arbitrary package/module execution. Package installation, entry points, manifests, persisted rows, and tenant defaults are not executable authorization.

## Quality and security policy

The active `main` ruleset requires these six strict contexts:

- `build (3.12)`
- `build (3.13)`
- `build (3.14)`
- `container-smoke`
- `diff-coverage`
- `container-supply-chain`

The release-authoritative aggregate metric is line coverage with an 85% floor. Critical modules also have explicit mandatory line/branch floors, and changed-production coverage is separately enforced. Hosted validation also runs focused accounting controls, dependency audits, secret scanning, container least-privilege/SBOM checks, and trusted-main attestations.

## Repository layout

- [`src/apps/`](../src/apps/README.md) — API, accounting services, observability, provider compatibility facade, and Streamlit workspaces.
- [`src/cli/`](../src/cli/README.md) — operational/demo CLI entry points.
- [`src/plugins/`](../src/plugins/README.md) — bundled reference provider and extension implementations.
- [`packages/provider-sdk/`](../packages/provider-sdk/README.md) — authoritative standalone provider author SDK distribution.
- [`scripts/`](../scripts/) — deterministic acceptance/demo helpers including the accountant close rehearsal.
- [`tests/`](../tests/README.md) — regression and policy suites.
- [`src/tools/`](../src/tools/README.md) — quality, audit, release, and security tooling.
- [`docs/`](README.md) — architecture, operations, examples, governance, and release evidence.

## Key workflows

- Install development dependencies: `python -m pip install -r requirements-dev.txt`
- Lint/format: repository Ruff commands / `make lint` where available
- Full quality gate: `make ci` or the repository-owned equivalent invoked by CI
- Audit snapshot: `make audit`
- Close rehearsal: `python -m scripts.accountant_close_pilot --output <new-output-dir>`
- Provider author acceptance: repository script/quality-gate path documented in `docs/guides/provider_sdk.md`

## Task management

`TASKLIST.md` is the authoritative concise active-task record. Historical completed task duplication and superseded design ideas must not remain presented as active work.

Current product-validation priority is issue #159, the real human-accountant close pilot. Open Dependabot PRs are independent maintenance work. Deployment/marketplace/production-platform ideas belong in the roadmap as conditional future scope until explicitly prioritized.

## Current known limits

- Human-accountant usefulness/friction review is **NOT RUN** until issue #159 is completed.
- Runtime schema setup still uses the local-demonstration `create_all` approach; migration-managed bootstrapping is a conditional deployment-hardening item, not a current portfolio blocker.
- Authentication lockout is sufficient for the current local boundary but not a shared distributed rate limiter for multi-worker/public deployments.
- The React directory is experimental and not part of the validated runtime.
- Provider SDK/governance is not a marketplace, certification program, remote installer, credential store, or production-provider approval.

## Dependency and automation stewardship

Requirements are tracked in `requirements.txt`, `requirements-dev.txt`, and the container lock. Dependabot opens bounded maintenance PRs; proposals must be evaluated from current `main` and must not be mixed casually into product slices. Major-version range widening requires explicit compatibility review.

Security guidance is in [`SECURITY.md`](SECURITY.md). Public-release evidence and historical baselines are in [`../PUBLIC_RELEASE_AUDIT.md`](../PUBLIC_RELEASE_AUDIT.md).

## Release documentation

- [`CHANGELOG.md`](CHANGELOG.md) records chronological repository changes.
- [`RELEASE_NOTES.md`](RELEASE_NOTES.md) describes the current delivered contracts and validation boundary.
- [`roadmap.md`](roadmap.md) separates near-term validation/maintenance from conditional future product or deployment scope.

No tag or GitHub Release is implied by documentation updates or merged feature PRs unless separately authorized.