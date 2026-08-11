# Reliability, Changed-Line Coverage, and Forecast Policy

This document records the issue #59 reliability tranche built on v0.2 `main` commit `4266ea43ed40201388df82bb53f757df45afe204`. It describes repository policy and measured evidence; it does not broaden the Early Beta / Portfolio Preview deployment claim.

## Changed-production-line coverage

The repository owns its changed-line evaluator:

```bash
python -m src.tools.diff_coverage coverage.json \
  --base <explicit-base-sha-or-ref> \
  --head HEAD \
  --config config/diff-coverage.toml \
  --json-output diff-coverage.json \
  --markdown-output diff-coverage.md
```

The equivalent Make target regenerates Coverage.py evidence first:

```bash
make diff-coverage BASE=<explicit-base-sha-or-ref>
```

Policy:

- configured production roots are `src/apps`, `src/plugins`, and `src/cli`;
- the changed executable line floor is 85%, equal to the release-authoritative aggregate line floor;
- base and head must resolve to Git commits;
- the evaluator uses the resolved merge base;
- added, modified, copied, and renamed target files are evaluated;
- deleted lines, comments, blank lines, documentation, and non-executable changed lines do not enter the denominator;
- a changed production file absent from coverage evidence fails closed;
- malformed policy, Git diff, or Coverage.py JSON fails closed;
- a diff with no changed executable production lines is reported as not applicable and passes explicitly rather than being silently skipped.

Pull-request CI checks out the exact head SHA and fetches the exact `github.event.pull_request.base.sha`. It writes deterministic JSON and Markdown evidence and uploads both with `coverage.json`. The workflow has read-only repository permission and uses full-SHA action pins.

At production-code head `a12fd25b684a5738fcf5fc2d0a604283a7434188`, changed-line coverage was 91.61%: 273 of 298 changed executable production lines were covered, above the 85% floor. The forecast router reached 100%; the hardened forecast boundary reached 90.94% on changed executable lines.

## Independent critical-module policy

Aggregate coverage cannot mask a critical accounting, authentication, background, provider, or forecasting regression. `config/critical-coverage.toml` independently enforces line and branch floors. Missing files, missing coverage records, and missing branch evidence fail closed.

Measured Python 3.14 results at production-code head `a12fd25b684a5738fcf5fc2d0a604283a7434188`:

| Critical module | Line result / floor | Branch result / floor |
| --- | ---: | ---: |
| Ledger service | 93.14% / 90% | 87.10% / 80% |
| Workflow service | 84.53% / 81% | 68.18% / 68% |
| Security boundary | 87.41% / 87% | 85.71% / 80% |
| Authentication sessions | 89.57% / 87% | 73.08% / 70% |
| Period lock | 96.43% / 85% | 92.86% / 70% |
| Close service | 91.65% / 85% | 82.39% / 70% |
| Reconciliation service | 91.94% / 85% | 81.37% / 70% |
| Close-evidence service | 95.16% / 85% | 81.25% / 70% |
| Close router | 93.68% / 85% | 78.12% / 70% |
| Tax service | 96.03% / 90% | 89.71% / 80% |
| Snapshot service | 91.37% / 85% | 70.00% / 60% |
| Audit router | 86.11% / 75% | 68.75% / 60% |
| Scheduler | 94.67% / 90% | 73.53% / 70% |
| Hardened forecast boundary | 90.13% / 78% | 77.97% / 60% |
| Forecast router | 100.00% / 75% | 100.00% / 60% |
| Provider loader | 93.33% / 88% | 84.00% / 70% |
| Bounded provider transport | 90.22% / 85% | 83.33% / 65% |

The preserved internal forecast model engine is not the authoritative public boundary. The validated wrapper and router own finite-value, cadence, timezone, output, and sanitized-error contracts and therefore carry the explicit forecast floors.

## Forecast reliability contract

The forecast service and API now enforce:

- finite target, regressor, intervention, prediction, metric, impact, p-value, and diagnostic numbers;
- deterministic duplicate timestamps using last supplied value wins;
- explicit one-point daily fallback and two-point observed-interval cadence;
- rejection of irregular cadence for three or more timestamps;
- rejection of mixed naive/aware timestamps and incompatible timezones;
- timezone-aware daily and hourly cadence across daylight-saving transitions;
- nonempty, trimmed, unique regressor names;
- regressor timestamps aligned to the target timeline, with no leading gap and no invalid-value-to-zero coercion;
- strictly increasing forecast timestamps and expected output lengths;
- nullable MAPE when any actual denominator is zero;
- ordered, contained causal-impact windows;
- bounded JSON-compatible diagnostics; and
- tenant authorization before any model discovery or forecast execution.

Expected service validation errors map to bounded allowlisted `400` responses. Unknown model-library errors map to a generic `400`. Logs include the operation and exception type only; raw exception text and request payloads are excluded.

See [`../FORECASTING.md`](../FORECASTING.md) for detailed service and API behavior.

## Historical issue #59 review reconciliation

The remaining historical review items are proven by current source and tests rather than duplicated:

| Review item | Current disposition and evidence |
| --- | --- |
| Snapshot data classification | `/snapshot`, `/snapshot/scenarios`, and `/snapshot/plans/preview` are authenticated shared-provider/cache computations with no organization identifier; they are not tenant financial-record routes. `tests/test_snapshot_api.py` covers all three surfaces, while `tests/test_token_type_boundary.py`, `tests/test_input_limits.py`, and `tests/test_request_body_limits.py` cover authentication and bounds. |
| Market/tax authorization before provider discovery | `tests/test_provider_authorization_order.py::test_provider_discovery_waits_for_tenant_membership` and `::test_provider_discovery_waits_for_manage_permission` prove provider resolution cannot run before tenant and role authorization. |
| Provider capability and loader validation | `tests/test_plugin_loader.py::test_load_provider_validates_required_methods`, `::test_load_provider_requires_name_attribute`, unknown-key/module/factory cases, compatibility descriptors, and `tests/test_provider_network_boundaries.py` cover trust and transport boundaries. |
| Trusted audit actor provenance | `tests/test_audit_actor_provenance.py::test_protected_route_derives_actor_from_authenticated_user`, `::test_protected_route_rejects_client_supplied_audit_identity`, and organization-binding tests prove server-derived identity and post-membership tenant attribution. |
| Collection, field, and numeric bounds | `tests/test_input_limits.py` covers forecast, backtest, causal-impact, scenario, workflow, posting, and metadata maxima. `tests/test_request_body_limits.py` covers the request-body boundary. Ledger/report suites preserve Decimal-safe accounting behavior. |
| Service validation to controlled 4xx | Forecast router tests cover allowlisted `400`, generic unknown-library `400`, tenant-first denial, and schema `422`; provider, ledger, report, workflow, and close API suites retain their domain-specific controlled mappings. |

The fail-closed route inventory remains the authoritative classification table. Forecast routes are tenant-member routes and the issue #59 router tests now cover authorization before forecast work for series, model discovery, backtest, and impact.

## Validation evidence

Permanent hosted workflows on production-code head `a12fd25b684a5738fcf5fc2d0a604283a7434188` passed:

- Python 3.12, 3.13, and 3.14 quality and accounting jobs;
- 686 tests;
- 52 focused accounting controls;
- 87.97% line coverage (`9,381/10,664`);
- 71.55% branch coverage (`1,925/2,690`);
- every configured critical-module floor;
- 91.61% changed-production-line coverage (`273/298`);
- Ruff lint and formatting;
- mypy;
- `pip check`;
- hashed runtime-lock and development dependency audits;
- current-tree secret scan;
- container supply-chain; and
- required container smoke and least-privilege checks.

No required quality tool was skipped. PR-event attestations remain skipped by design; trusted-main events own attestation publication. Documentation-only reconciliation commits must repeat the permanent exact-head workflows before merge readiness.

## Scope boundary

This policy does not include:

- Ruff 0.16 migration, which remains issue #102;
- a repository-wide numeric branch floor;
- live model downloads or network tests;
- a provider marketplace;
- close-workspace product expansion; or
- LAN, reverse-proxy, or public-hosting approval.
