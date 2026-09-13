# Release Notes

## Current main — Early Beta / Portfolio Preview

Current repository baseline after merged PR #158: `f8c8c5d1498c612cce4f50905362cd682310399e`.

The repository is a portfolio-grade accounting-control toolkit. It is not a full ERP, production tax engine, bank-feed product, treasury system, provider marketplace, regulated financial product, or commercially supported accounting platform. The validated deployment boundary remains local/loopback demonstration unless a separate deployment review expands that claim.

### Current delivered scope

- **v0.2 Accountant Close Workspace:** controlled accounting periods, serialized posting/close gates, reconciliations, current variance review, independent journal approvals, checklist/readiness, deterministic evidence, explicit lifecycle transitions, and browser-tested Streamlit controls.
- **v0.3 Provider SDK/conformance:** bounded immutable manifests; bank/FX/macro/market/tax structural contracts; deterministic fail-closed conformance; allowlist-enforced provider loading; bundled-provider adoption; scaffold/CLI evidence; compatibility documentation; and critical coverage.
- **v0.4 Provider Catalog Governance:** persistent trusted-registration evidence, organization enablement/default policy, revision-protected audited mutation, credential-presence-only readiness, allowlist-enforced resolution, authenticated API/Streamlit administration, and deterministic secret-free evidence.
- **v0.5 Provider Author Kit:** installable `modular-accounting-provider-sdk`, authoritative in-tree PEP 517 backend, typed standalone scaffold/validate/build CLI, conventional provider wheel/sdist projects, deterministic artifacts, clean author/consumer acceptance, and an identity-preserving application facade.
- **Accountant close rehearsal and pilot kit — PR #156:** repeatable isolated close rehearsal, deterministic seed/walkthrough, role-by-role guidance, evidence capture, posting-freeze/reopen proof, and an intentionally unfilled human-review worksheet.
- **Close Workspace UX correction — PR #158:** immediate refresh of server-backed close tables/panels, immediate sanitized denial feedback, and stable active-tab behavior across Streamlit reruns.

### Current validation

PR #158 merged to `main` with the exact accepted source tree. Its final PR acceptance reported:

- Python 3.14.0 / Streamlit 1.63.0 supported-Windows validation;
- 17 focused Close Workspace tests and 896 full-suite tests passing;
- actual Chrome 152 acceptance at 1440×1000 and 390×844;
- immediate `CLOSE_CONFLICT` denial feedback with HTTP 409, zero SQL writes, and unchanged persisted-table state;
- 19/19 changed executable production lines covered;
- 52 focused accounting controls passing;
- release-authoritative line coverage above the 85% floor;
- all configured critical-module line/branch floors passing;
- Ruff, formatting, configured mypy, provider-author acceptance, `pip check`, runtime/dev dependency audits, secret scanning, container smoke, and supply-chain validation passing.

The trusted-main post-merge CI run `34738382100` passed Python 3.12/3.13/3.14, container supply-chain, accounting controls, and main-only container provenance/SBOM attestations.

### Remaining validation

Human-accountant review is **NOT RUN**. Issue #159 is the next product-validation step. The reviewer should use the existing synthetic close, walkthrough, and worksheet to record actual setup friction, control clarity, evidence usefulness, role-switching friction, and measured workflow time. Automated/AppTest/browser evidence must not be substituted for human judgment.

If #159 exposes defects, fix only demonstrated gaps and re-pilot as needed. If the pilot is satisfactory, the repository should be treated as complete for its current Early Beta / Portfolio Preview scope.

## Provider trust boundary

`settings.allowed_providers` remains the only executable provider trust source. Package installation, importability, manifests, entry points, persisted registrations, organization policy, and defaults cannot self-authorize Python code. Persisted governance may narrow trusted execution and retain safe evidence, but it may never broaden executable trust.

The standalone provider SDK remains a structural authoring/conformance tool. No provider package is published by this repository, and no marketplace, registry, signing/revocation service, certification program, or production-provider approval is implied.

## Quality and merge policy

The active `main` ruleset requires squash-only pull requests, resolved review threads, linear history, no force pushes or deletion, and six strict GitHub Actions contexts:

- `build (3.12)`
- `build (3.13)`
- `build (3.14)`
- `container-smoke`
- `diff-coverage`
- `container-supply-chain`

Aggregate release-authoritative line coverage has an 85% floor. Aggregate branch coverage is diagnostic, while configured critical modules have explicit mandatory line/branch floors. Changed-production coverage is separately enforced.

## Maintenance

Open Dependabot PRs #150-#153 are maintenance proposals created before the latest close-pilot merges and must be refreshed/re-evaluated from current `main` before merge consideration. Ruff/build and the SBOM action are ordinary maintenance; pandas and mypy widen accepted major-version ranges and require explicit compatibility review.

## Conditional future deployment work

The following are not blockers for the current local portfolio product. They become relevant only if the deployment/product claim expands:

- Alembic-managed schema migrations and migration bootstrapping;
- shared/distributed auth rate limiting and optional MFA based on threat model;
- database-native multi-writer close/posting locks;
- PostgreSQL/reverse-proxy/public-hosting deployment acceptance;
- production OTLP/alerting examples and broader operational instrumentation;
- a production web client replacing the experimental React placeholder.

## Release decision

The project remains **Early Beta / Portfolio Preview**. No tag, GitHub Release, production certification, public/LAN deployment approval, marketplace approval, or regulatory-compliance claim is created by these notes.