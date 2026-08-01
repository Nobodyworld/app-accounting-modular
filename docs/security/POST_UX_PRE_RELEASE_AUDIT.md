# Post-UX Pre-Release Security Audit

## Status and executive result

**Final code-audit reconciliation complete; deployment approval remains scoped.**
This is the evidence record for issue #87 and draft PR #105. The exact audited
application baseline is `65ee0f8399eb5c7146db63b3726ab4ca8ac03467` on
`main`. PR #105 remains draft and unmerged, and issue #87 remains open for
owner review of this evidence and disposition.

The audit identified nine actionable findings across its initial and final
tranches: zero Critical, three High, six Medium, zero Low, and zero
Informational. All nine are resolved on the audited baseline; the open count is
zero at every severity. The remaining limitations in this report are operator
or deployment assumptions, not undisclosed code findings.

Final worktree evidence is green:

- 151 focused audit/remediation tests passed with no skip or failure-expectation
  marker;
- 575 complete tests and 52 accounting-control tests passed;
- line coverage is 88.71% (7,109/8,014) against an 85% gate and branch evidence
  is 73.87% (1,473/1,994);
- Ruff, format, mypy, clean-environment `pip check`, both dependency audits,
  Bandit review, full-history Gitleaks, and the current-tree secret scan passed;
- the fail-closed route inventory maps 40 method/path entries;
- trusted `main` push run
  [30712271225](https://github.com/Nobodyworld/app-accounting-modular/actions/runs/30712271225)
  passed the Python 3.12/3.13/3.14 quality and accounting jobs,
  `container-supply-chain`, and all four archive attestations.

This audit supports local nonproduction demonstration and conditional use on a
controlled trusted-team workstation. It does not approve LAN or public hosting.
Reverse-proxied containers require a deployment-specific review and the
operator controls listed below.

## Exact baseline and reconciliation

The required preflight passed before mutation:

| Ref | SHA |
| --- | --- |
| Starting audit branch | `14cb1d359dea55b31a730d645cbca4f3056fb166` |
| `origin/main` / audited application | `65ee0f8399eb5c7146db63b3726ab4ca8ac03467` |
| Shared merge base | `926e0057cdc7676ac1cb006502a37fdf651bbb42` |

The primary worktree was clean and already on
`security/post-ux-pre-release-audit`. `origin/main` was merged with `--no-ff`
as `d64cfd96571a480054eb56acfa4def35cb130503` using
`merge: reconcile audit with remediated main`. Git's `ort` strategy merged
`tests/test_security_integration.py` automatically; there were no manual
conflict files. No reset, clean, restore, stash, rebase, force-push, amend, or
history rewrite was used.

The final audit-branch SHA is intentionally not embedded in the commit that
creates it. It is recorded in the PR evidence and final reconciliation report
after the branch is pushed.

## Threat model and trust boundaries

Protected assets include passwords and password hashes; access and refresh
tokens; signing material and session identifiers; users, memberships, roles,
and organization data; ledger, budget, report, forecast, workflow, scenario,
snapshot, tax, FX, market, and audit records; provider credentials and output;
uploads and CSV exports; database and cache state; logs, traces, metrics, and
container evidence.

Reviewed boundaries are browser-to-Streamlit, Streamlit-to-FastAPI, public to
authenticated routes, JWT validation to persisted session lookup,
authentication to tenant/role authorization, routers/services to SQLModel
transactions and caches, provider allowlist to external HTTPS services,
request handling to scheduler/background sessions, host to container
filesystems and volumes, reverse proxy to application listeners, and source
control/package registries to CI artifacts and attestations.

The attacker model includes anonymous callers probing public diagnostics,
authenticated cross-tenant callers, malicious members submitting expensive or
export-active data, compromised provider responses, forged identity headers,
local unprivileged users, LAN attackers after an unsafe bind change, operator
misconfiguration, and dependency/workflow compromise. Operator-controlled
provider modules remain trusted Python code by design.

## Complete remediation history

| Finding | Severity | Resolution | Merge evidence |
| --- | --- | --- | --- |
| #90: Compose exposed all interfaces and used a repository-known signing key | High | Loopback-only publication, mandatory explicit secret, fail-closed Compose | PR #92 / `acfe9b27a43b72889171350ae94599864320fe75` |
| #93: client identity headers could forge audit attribution | High | Authenticated audit principal binding and rejection of public identity headers | PR #94 / `2a4d07c128c8bd378662b185f534025905714c9e` |
| #91: containers ran as root without least-privilege controls | Medium | UID/GID 10001, read-only roots, capability drop, `no-new-privileges`, bounded writes | PR #96 / `35292ea58555e7a8a35d054f98ebd95566c9129f` |
| A87-001 / #106: refresh token accepted as access token | High | Access/refresh token-type separation | PR #112 / `b83f18bb9a13ab490518839bdb7f66f25247dd96` |
| A87-002 / #107: provider discovery preceded tenant authorization | Medium | Organization and role authorization now precede market/tax provider resolution | PR #113 / `0cf07b30ee9aff8b1a375dc90e4d3150b402e288` |
| A87-003 / #108: CSV formula injection | Medium | Central spreadsheet-safe text neutralization for `=`, `+`, `-`, and `@` | PR #114 / `78b44d11d7fe444eee2c74c20198a9e4d9b3b437` |
| A87-004 / #109 and #118: unbounded inbound and outbound work | Medium | Request, collection, metadata, upload, provider byte/record/timeout/retry bounds | PR #119 / `87f1323a88bedb0aa0e032198e0ad3da5a1c2703`; PR #121 / `0b7a6d6b333bfb7dca9be21ce956e0000db359dd` |
| A87-005 / #110: no persisted revocation or refresh rotation | Medium | Persisted sessions, one-time refresh rotation/replay revocation, logout, admin revocation, cleanup, Streamlit lifecycle | PR #120 / `4567936f200b065ba246eb80ca2f6bbfc4d1ff4a` |
| A87-006 / #111: mutable and unlocked container supply chain | Medium | Digest-pinned base, hashed runtime/tool locks, fail-closed install, SBOM/checksum/attestation workflow | PR #124 / `65ee0f8399eb5c7146db63b3726ab4ca8ac03467` |

The initial three findings were recorded in issue #87's connector audit tranche
and were merged before the original audit branch was created. They remain in
this chronology so the final report does not silently discard earlier audit
work.

## Authentication and session security

- Access and refresh JWTs have distinct `type` claims and are rejected at the
  opposite boundary with the same generic credential error.
- Protected access requires a matching active `AuthSession`; signature validity
  alone is insufficient. The session must exist, belong to the subject user,
  remain unexpired/unrevoked, and the user must remain active.
- Refresh is one-time compare-and-swap rotation of the stored refresh-JTI
  digest. Reuse revokes the whole session family, including the successfully
  rotated pair.
- `POST /auth/logout` revokes only the current access-token session and records
  an audit event. Invalid or already revoked sessions receive generic `401`.
- Same-organization administrators can revoke a member session. Missing and
  cross-tenant targets return nondisclosing `404`; repeat revocation is
  idempotent.
- Login and refresh opportunistically delete bounded expired-session batches;
  the hourly `auth-session-cleanup` scheduler job provides scheduled cleanup.
- Streamlit retains access, refresh, and session identifiers only in memory,
  rotates the pair atomically, retries one protected request at most once,
  attempts server logout first, and always clears local protected state.

Negative coverage preserves non-bearer authorization, malformed JWT, invalid
signature, unsupported algorithm, expiration, missing/malformed/nonexistent
subjects, deleted/inactive users, generic errors, and signing-key/traceback
nondisclosure. Valid protected requests use real persisted sessions. The access
boundary test uses a real refresh token from a login/session pair and receives
generic `401`.

The remaining login lockout limitation is operational: failure counters and
five-minute lockouts are process-local memory. They reset on restart and do not
coordinate across workers or hosts. Public/multi-worker operation requires an
edge or shared distributed rate-limit control.

## Tenant and provider authorization

The generated [route inventory](evidence/route-inventory.md) imports the actual
FastAPI application, traverses dependencies, applies exact policies, and fails
for either an unmapped route or stale policy. It was generated twice with
identical output.

| Classification | Entries |
| --- | ---: |
| Public | 17 |
| Authenticated only | 4 |
| Tenant member | 6 |
| Tenant manager | 11 |
| Tenant administrator | 2 |
| **Total** | **40** |

The total includes GET and HEAD for four framework schema/documentation paths;
32 entries are application routes. Market and tax organization membership and
route-specific management checks execute before provider discovery. Cross-
tenant provider probes are denied before provider state can be disclosed.

`GET /snapshot`, `POST /snapshot/scenarios`, and
`POST /snapshot/plans/preview` are authenticated shared-provider/cache routes.
They accept no organization identifier and are not represented as tenant-scoped
data authorization. Health, providers, metrics, telemetry, extension metadata,
and framework diagnostics remain public in code and require reverse-proxy or
network restriction in nonlocal deployments.

Newly mapped authentication routes are:

- `POST /auth/refresh`: public refresh-token input; persisted lookup, atomic
  rotation, reuse detection/family revocation, and rotated pair/session output;
- `POST /auth/logout`: authenticated current-session revocation and audit event;
- `POST /auth/sessions/{session_id}/revoke`: same-organization tenant
  administrator, nondisclosing lookup, idempotent revocation.

## Input, upload, output, and provider boundaries

The application enforces these hard maxima before expensive work:

| Boundary | Maximum |
| --- | ---: |
| FastAPI request body | 2,097,152 bytes; operator may only lower it |
| Forecast/backtest/impact series and each regressor/intervention series | 10,000 points |
| Regressor/intervention fields | 32 |
| Backtest models | 16 |
| Forecast/backtest horizon | 365 |
| Backtest initial window or step | 10,000 |
| Direct or plan scenarios | 100 |
| Symbols or jurisdictions per scenario | 64 each |
| Tags / characters per tag | 64 / 128 |
| Workflow transactions / postings per transaction | 100 / 100 |
| Staged IDs per process request | 500 |
| Metadata depth / keys per mapping / nodes / string characters | 6 / 128 / 2,048 / 4,096 |
| Streamlit upload | 1,048,576 bytes; framework defense-in-depth cap is 2 MB |
| Direct-provider body / FX records | 1,048,576 bytes / 512 |
| YFinance rows / date range | 10,000 / 10,000 days |

Request bodies check declared length and independently count the ASGI stream.
Uploads check reported size before materialization, otherwise read only
`limit + 1`, recheck retained bytes, and clear stale input/results on rejection.
CSV text fields beginning with dangerous spreadsheet prefixes are neutralized
without changing numeric negative values.

Direct HTTPS providers use 5-second connect and 20-second read timeouts,
64-KiB bounded streaming chunks, and at most two attempts with a 0.05-second
backoff for connection/timeouts or HTTP 429/502/503/504. Other 4xx responses,
oversized responses, and invalid payloads are not retried. Stable exceptions and
structured logs omit response bodies, raw upstream errors, credential-bearing
URLs/parameters, authorization headers, and secrets.

YFinance uses its high-level `download` API once with threads disabled, passes a
20-second timeout when supported, validates symbol/date range, bounds the
materialized row count, and sanitizes failures. That API does not expose the raw
HTTP response, so the application cannot independently enforce byte-level
streaming on YFinance. This is a documented third-party boundary, not a claim
that the response body is byte-bounded.

## Persistence and audit integrity

The accounting and focused suites cover balanced posting, rollback, tenant
object scope, organization-scoped idempotency, report/cache isolation, workflow
retry, tax stale-deletion scope, session rotation/revocation races, cleanup
rollback, and scheduler containment. No integrity or cross-tenant failure was
demonstrated. SQLite is the exercised database. Audit records have no mutating
API, but database operators remain trusted and the audit store is not append-
only or tamper-evident.

## Container and supply chain

Both images use
`python:3.14-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6`.
The 84-package (19 direct, 65 transitive) runtime lock is exact and hashed;
SHA-256 is `990aa39c04686870f6907074b32d01eff81f69f84f9281d98aefa91fb72163d9`.
The `uv==0.12.0` lock-tool artifact is also exact/hashed; lock SHA-256 is
`2522c140fe61233b873b30a8cb54e613e80f2c4bea1ea39f64e21f37b2a4d51a`.

Images install only binary wheels with `--require-hashes --only-binary=:all:
--no-deps`; there is no installation-time dependency resolution or pip upgrade.
Each build runs `pip check`, and hosted evidence compares the installed package
inventory with the lock. Syft 1.50.0 produces separate SPDX JSON image SBOMs,
and the workflow verifies archive, SBOM, and runtime-lock checksum manifests
before upload and again before attestation.

All Actions are executable only at full commit SHAs; Dependabot covers pip,
Actions, and Docker. Images are not published to a registry, so attestations are
bound to exported archives, not registry images. The workflow does not promise
bit-for-bit Docker image IDs because build timestamps and other metadata are not
normalized.

The separate required `container-smoke` compatibility run
[30692461341](https://github.com/Nobodyworld/app-accounting-modular/actions/runs/30692461341)
passed on PR #124 head `55f7d92850e855bca124ecab69c97c45510ebf4d`.
The trusted post-merge `main` run's expanded `container-supply-chain` job passed
build, health, UID/GID 10001, read-only roots, dropped capabilities,
`no-new-privileges`, intended `/data` and `/tmp` writes, installed-package
verification, archive export, SPDX generation, checksum validation, and teardown.

## Trusted-main artifact and attestations

Trusted run metadata:

| Field | Value |
| --- | --- |
| Run | `30712271225` / <https://github.com/Nobodyworld/app-accounting-modular/actions/runs/30712271225> |
| Event / exact head | `push` / `65ee0f8399eb5c7146db63b3726ab4ca8ac03467` |
| Artifact | `container-supply-chain-evidence-65ee0f8399eb5c7146db63b3726ab4ca8ac03467` |
| Artifact ID / size | `8822272326` / `1,913,560,525` bytes |
| Artifact digest | `sha256:b46833ac5bcc7af93218f553f5377789f2c0efa555169a4b11219811c1b3d28d` |
| Retention | 14 days; API expiry `2026-08-15T18:21:46Z` |

Evidence checksums:

| Evidence | SHA-256 |
| --- | --- |
| API image archive | `e7348319a275340c2c94ef39cee9e9f00850558993d898a597849afa10b7bcaa` |
| Web image archive | `1ecf2e934c81bd03077a362d0aec32eb456d327c057d95685211b7fc25ebc19b` |
| API SPDX SBOM | `53cd24c7d3cbde22d7e7e276d7128d89348bc92ca50f5b47d2bace45d774c5ca` |
| Web SPDX SBOM | `1d6fc9f0b91e49042c264b851881718e57832ef136c791fab716530f5fbdffe4` |
| Runtime lock | `990aa39c04686870f6907074b32d01eff81f69f84f9281d98aefa91fb72163d9` |

Published attestations:

| Subject | Provenance | SPDX SBOM |
| --- | --- | --- |
| API archive | [38347213](https://github.com/Nobodyworld/app-accounting-modular/attestations/38347213) | [38347236](https://github.com/Nobodyworld/app-accounting-modular/attestations/38347236) |
| Web archive | [38347258](https://github.com/Nobodyworld/app-accounting-modular/attestations/38347258) | [38347271](https://github.com/Nobodyworld/app-accounting-modular/attestations/38347271) |

The artifact ZIP and its three checksum manifests were independently verified
after download. Two direct `gh run download` attempts were interrupted by the
network; the authenticated, resumable Artifact API fallback produced a ZIP
whose SHA-256 exactly matched the artifact digest above. GitHub CLI 2.81.0 was
used after consulting local
`gh attestation verify --help`. Both archives passed repository-scoped
provenance verification and SPDX predicate verification with source digest
`65ee0f8399eb5c7146db63b3726ab4ca8ac03467`, source ref `refs/heads/main`, and
signer workflow `.github/workflows/ci.yml`. Four strict verification commands
(API and Web provenance plus API and Web SPDX) completed successfully with
exit code 0.

## Quality, dependency, static, and secret evidence

The authoritative environment was freshly created at
`C:\tmp\app-accounting-final-audit-65ee0f8` from `requirements-dev.txt`, with
Bandit added only as the audit scanner. It used Windows 11 build 26200, Python
3.14.0, pip 25.2, Git 2.51.2.windows.1, Ruff 0.15.21, mypy 1.20.2, pytest
9.1.1, pip-audit 2.10.1, Bandit 1.9.4, Gitleaks 8.30.1, and GitHub CLI 2.81.0.

`python -m src.tools.quality_gate` passed in that clean environment: Ruff lint,
Ruff format (214 files), mypy (62 source files), 575 tests, the coverage gate,
52 accounting controls, `pip check`, both dependency audits, and the current-
tree secret scan. The explicit complete suite also passed 575 tests with two
framework deprecation warnings. The focused audit/remediation command passed
151 tests. No test was skipped.

The dependency results were:

- `pip check`: no broken requirements;
- hashed runtime-lock `pip-audit`: no known vulnerabilities;
- development-manifest `pip-audit`: no known vulnerabilities.

Bandit scanned 15,408 lines and returned 18 Low tool results, zero Medium/High:
B101 (5), B105/B106 (3), B110/B112 (6), and B404/B603 (4). Every location was
reviewed. The asserts are internal initialized-worker/model invariants rather
than access checks; token/session key names and `bearer` are identifiers, not
credentials; suppressed exceptions are destructor/optional-library cleanup,
invalid model candidates, or metrics/diagnostic fallbacks; and developer-tool
subprocess calls use fixed argument sequences with `shell=False`. No result is
an actionable security finding. Temporary JSON SHA-256 is
`7532b1c312330c7adad1515006a9d0a6b78027d4663a1e5c7ef66e5aa081323e`.

Gitleaks scanned all refs from root
`b026d0accd565f78f2dfc012daa5790352aece8f` through committed pre-signoff HEAD
`d64cfd96571a480054eb56acfa4def35cb130503`. Git contained 285 reachable
commits and Gitleaks reported 268 commits
processed, approximately 3.21 MB, zero findings, and therefore no false-positive
or credential-response action. Empty report SHA-256 is
`37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570`.
The current-tree scanner separately reported no high-confidence secret pattern.

Trusted-main Python 3.14 evidence at the exact application baseline passed 556
tests, 52 accounting controls, 88.67% line coverage (7,106/8,014), and 73.82%
branch evidence (1,472/1,994); all quality/dependency/secret commands passed.
The Python 3.12 and 3.13 jobs also completed successfully. These baseline
figures are distinguished from the 575-test final audit-branch result.

Semgrep was unavailable and was not installed globally. Docker and Docker
Compose were unavailable on the audit host, so no local image build/start or
runtime check is claimed. Hosted exact-SHA container evidence is the runtime
source described above.

## Findings register

| Severity | Discovered | Resolved | Open |
| --- | ---: | ---: | ---: |
| Critical | 0 | 0 | 0 |
| High | 3 | 3 | 0 |
| Medium | 6 | 6 | 0 |
| Low | 0 | 0 | 0 |
| Informational | 0 | 0 | 0 |

All actionable issue #87 findings are resolved in the application baseline.
This does not convert deployment prerequisites into code guarantees.

## Deployment disposition

| Mode | Disposition | Conditions and limits |
| --- | --- | --- |
| Local nonproduction demonstration | **Suitable** | Preserve loopback binding; use generated/nonproduction identities and data; supply an explicit secret for Compose; do not treat ephemeral-secret direct runs as persistent sessions |
| Trusted-team workstation | **Conditionally suitable** | Controlled host/accounts, durable secret management and rotation, protected database/files, backups and restore tests, log access/retention, approved data retention, monitoring, and incident response |
| LAN deployment | **Not approved by this audit** | Requires a separate architecture/runtime review for TLS, trusted hosts/proxies, firewall/ACLs, shared rate limiting, durable secrets, production database, monitoring, backup/restore, and public diagnostic restriction |
| Reverse-proxied container deployment | **Not approved by repository defaults; eligible for deployment-specific review** | Container evidence is green, but the proxy/TLS/forwarded-header/host/body-limit policy and production data controls were not exercised end to end |
| Public hosting | **Not approved** | No public-hosting penetration test, distributed abuse controls, production database/secret/backup/monitoring evidence, data-retention policy, or verified diagnostic-surface restriction |

## Residual operator assumptions and warnings

- Terminate TLS with reviewed certificates; configure trusted hosts and a
  narrow forwarded-proxy policy; enforce equal or smaller edge body limits.
- Restrict listeners and public diagnostics with firewall/network ACLs and
  reverse-proxy rules. Do not expose the default Compose profile beyond
  loopback.
- Generate, store, rotate, and recover durable JWT/provider secrets without
  committing or logging them.
- Select and harden a production database; provide encryption at rest, least-
  privilege database credentials, backups, and tested restores.
- Define log/metric access, redaction, retention, alerting, incident response,
  and data-retention/deletion policy.
- Provide distributed login/request rate limiting for multi-worker or public
  operation; the application login lockout is process-local.
- Run deployment-specific load, failure, and penetration testing before any
  public claim. SQLite-only local tests are not production-database evidence.
- Restrict or disable public health, provider, metrics, telemetry, extension,
  OpenAPI, Swagger, and ReDoc surfaces when the operating model does not require
  anonymous access.
- YFinance's high-level client prevents independent raw response-byte
  enforcement; retain row/date/timeout controls and monitor dependency changes.
- Two local framework warnings remain: Starlette's TestClient/httpx transition
  and the deprecated HTTP 422 constant. They do not weaken an authorization or
  accounting control.
- The shared host Python was nonauthoritative because unrelated `opencv-python`
  and old Streamlit installations conflict with NumPy/Pillow. The clean
  manifest-derived environment passed. Semgrep and local Docker were skipped as
  described; no success is claimed for them.

## Final sign-off boundary

The application-code findings are resolved and the required audit evidence is
complete. The evidence supports the scoped dispositions above, not a general
release or public-hosting approval. PR #105 must remain draft and unmerged and
issue #87 must remain open until the owner and GitHub connector review the final
branch SHA, exact-head CI, hosted artifact/attestation evidence, and operator
assumptions.
