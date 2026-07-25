# Post-UX Pre-Release Security Audit

## Status

**In progress — High finding A87-001 is open and no release-security conclusion
has been reached.** This report is the evidence record for issue #87 and draft
PR #105. The PR must remain draft and unmerged. Issue #87 must remain open.

The audited application tree is `main` at
`926e0057cdc7676ac1cb006502a37fdf651bbb42`. Checks in this report were run from
the audit branch starting commit
`165eb3a007f83edabf17450675ea83978c5b4c9b`, whose only committed change over
that application tree was this report scaffold.

## Executive result

- A valid refresh token is accepted as an access token by protected routes.
  This is High finding A87-001 / issue #106 and blocks every release-ready claim.
- No cross-tenant financial-data read or write was demonstrated by the executed
  tenant and object-scope tests.
- Five additional Medium findings cover provider-discovery ordering, CSV formula
  injection, unbounded expensive inputs/uploads, absent session revocation and
  refresh rotation, and non-reproducible container dependency resolution.
- The isolated full quality gate passed: 406 tests, 88.31% line coverage,
  72.40% branch coverage, 52 focused accounting-control tests, lint, format,
  mypy, dependency resolution, dependency audit, and current-tree secret scan.
- The all-history Gitleaks scan covered 227 commits and found no leaks.
- Docker is not installed on the audit host. Local container execution is
  blocked; exact-head hosted container CI remains required evidence.
- The repository is not release-ready. Local demonstration remains the only
  documented operating boundary, subject to the open findings and nonproduction
  data/identity restrictions.

## Exact-SHA preflight and repository integrity

Preflight was run before testing:

```text
git fetch origin --prune
git status --short
git branch --show-current
git rev-parse HEAD
git rev-parse origin/security/post-ux-pre-release-audit
git rev-parse origin/main
git diff --check
```

Result: **PASS**. The checkout was clean on
`security/post-ux-pre-release-audit`; local and remote audit HEAD were both
`165eb3a007f83edabf17450675ea83978c5b4c9b`; `origin/main` was
`926e0057cdc7676ac1cb006502a37fdf651bbb42`; `git diff --check` was clean.
No worktree isolation, reset, clean, restore, stash, or rebase was used.

The baseline integrity procedure also ran:

```text
git status --short
git rev-parse HEAD
git log --oneline --decorate -n 25
git fsck --full
```

`git fsck --full` completed without corrupt or missing reachable objects. It
reported dangling commits, trees, a blob, and a tag; these are ordinary
unreachable local objects and were not modified or pruned.

## Environment and tool inventory

| Tool | Version / status | Source and use |
|---|---|---|
| Operating system | Windows 11 Home 64-bit, 10.0.26200 build 26200 | Audit host |
| Python | 3.14.0 | Host and isolated audit venv |
| pip | 26.1.2 | Host and isolated audit venv |
| Git | 2.51.2.windows.1 | Repository checks |
| GitHub CLI | 2.81.0 | Authenticated read-only configuration/CI checks and issue fallback |
| Docker | Not installed | Dynamic container work blocked locally |
| Docker Compose | Not installed | Dynamic container work blocked locally |
| Docker SBOM | Not installed | Image SBOM blocked locally |
| Gitleaks | 8.30.1 | Host binary; all-history scan |
| Ruff | Host 0.14.2; isolated 0.15.21 | Repository pin used for authoritative gate |
| mypy | Host 1.18.2; isolated 1.20.2 | Isolated authoritative gate |
| pytest | 9.1.1 | Isolated authoritative gate |
| pip-audit | Host 2.7.3; isolated 2.10.1 | Repository pin used for authoritative audit/SBOM |
| Bandit | 1.9.4 | Installed from PyPI in isolated venv |
| CycloneDX CLI | 7.3.1 | Installed as `cyclonedx-bom` from PyPI in isolated venv |
| Semgrep | Not installed; skipped | No global installation attempted |
| Syft | Not installed; skipped | No global installation attempted |

The isolated environment is
`C:\tmp\app-accounting-audit-165eb3a`. It was created with `python -m venv`
and populated from `requirements-dev.txt` plus `bandit` and `cyclonedx-bom`
from PyPI. No global tool was installed.

## Evidence index

| Area | Evidence | Status | Result / finding |
|---|---|---:|---|
| Threat model and trust boundaries | This report | Complete for audited code; deployment assumptions explicit | Six findings |
| Route inventory | [`evidence/route-inventory.md`](evidence/route-inventory.md) | Complete | 37 method/path entries; no unmapped app route |
| Authentication/session negatives | Focused pytest and sanitized proof | Partial | A87-001 High; A87-005 Medium |
| Tenant isolation | Focused pytest and route review | Partial | No cross-tenant data access; A87-002 Medium |
| Input/upload/error/export | Focused pytest and schema/export review | Partial | A87-003 and A87-004 Medium |
| Persistence/concurrency/idempotency | Quality gate and focused service/API tests | Pass with limitations | No demonstrated integrity failure |
| Provider/background boundaries | Code review and focused pytest | Partial | A87-002, A87-004; upstream bounds absent |
| Network/proxy/CORS/headers | TestClient and static deployment review | Partial | Public/LAN modes unsupported |
| Full-history secrets | Gitleaks 8.30.1 | Pass | 227 commits, zero findings |
| Dependency and supply chain | pip check, pip-audit, workflow/config review | Partial | A87-006 Medium |
| GitHub configuration | GitHub API/CLI read-only queries | Partial | Ruleset/scan controls recorded; no code-scanning analysis |
| Container/runtime | Static Compose/Dockerfile tests | Blocked locally | Docker unavailable; hosted CI required |
| SBOM | pip-audit CycloneDX JSON in temporary storage | Pass with limitations | 121 components; no hashes/licenses/PURLs |
| Static analysis | Bandit 1.9.4 plus manual review | Pass with reviewed Low results | 18 Low, no actionable Bandit finding |

## Quality and accounting validation

The required host-environment command:

```text
python -m src.tools.quality_gate
```

was **partial/fail** only because host `pip check` found an unrelated installed
package conflict: `opencv-python 4.12.0.88` requires NumPy below 2.3 while the
host had NumPy 2.3.4. Every repository check in that run passed.

The same exact command then ran in the isolated manifest-derived environment
before audit-only tests were added and **passed**:

- Ruff check: pass;
- Ruff format check: pass, 187 files;
- mypy: pass, 56 source files;
- pytest: 406 passed;
- release-authoritative line coverage: 88.31% (6,420/7,270);
- diagnostic branch coverage: 72.40% (1,283/1,772);
- focused accounting controls: 52 passed;
- `pip check`: no broken requirements;
- pip-audit 2.10.1: no known vulnerabilities;
- current-tree secret scan: no high-confidence patterns;
- skipped quality-gate tools: none.

Warnings were one Starlette/httpx deprecation, one deprecated HTTP 422 constant,
and intermittent unclosed SQLite `ResourceWarning` evidence. They did not fail
the gate; the SQLite warning is a cleanup signal but did not demonstrate data
loss or cross-test contamination.

After audit-only tests were added, the focused security/tenant/input/persistence
suite passed **92 tests with 10 strict expected failures** and one deprecation
warning. The final complete pre-commit quality gate then passed **415 tests with
10 strict expected failures**, 88.40% line coverage (6,427/7,270), 72.57% branch
coverage (1,286/1,772), and the same 52/52 accounting-control tests. Expected
failures map only to A87-001 through A87-004 and are not remediation or
suppression.

## Threat model

### Assets

- passwords and PBKDF2 password hashes;
- access and refresh tokens, signing material, and session identifiers;
- users, active state, organization membership, and role flags;
- ledgers, accounts, transactions, postings, budgets, reports, forecasts,
  workflow staging records, scenario plans, snapshots, and audit records;
- provider allowlists, provider credentials, adapter output, FX, market, tax,
  and externally sourced financial data;
- uploaded scenario-plan and budget files held in Streamlit session memory;
- generated CSV exports and cached report output;
- SQLite/database files, provider/report/application caches, and container
  volumes;
- logs, traces, metrics, health details, request identifiers, and audit evidence.

### Trust boundaries

- browser to Streamlit, including upload/download and client session state;
- Streamlit to FastAPI over the configured `API_BASE`;
- anonymous/public routes versus OAuth2 bearer parsing;
- bearer parsing to `get_current_user`, then authenticated audit context;
- user authentication to organization membership and route-local role checks;
- routers/services to SQLModel sessions, commits, rollbacks, and caches;
- caller-selected provider keys to the operator-controlled allowlist, dynamic
  module import, provider factories, and external HTTPS services;
- request lifecycle to FastAPI background tasks and APScheduler sessions;
- host filesystem to container read-only roots, `/tmp`, `/data`, and volumes;
- reverse proxy/TLS/host/forwarded headers to Uvicorn/Streamlit;
- CI workflows and mutable package/base-image registries to built artifacts.

### Attacker profiles

- anonymous remote caller probing public health, schema, provider, telemetry,
  metric, extension, and login surfaces;
- authenticated user probing another organization or object identifier;
- malicious tenant member sending expensive inputs or crafted export values;
- malicious tenant administrator abusing management/provider/background actions;
- forged identity-header sender attempting audit actor spoofing;
- compromised or malformed external provider;
- local unprivileged host user reading files, process output, or mounted data;
- LAN network attacker when loopback bindings are changed;
- operator misconfiguration of signing keys, algorithms, proxy trust, TLS,
  writable paths, provider allowlists, or logging;
- dependency, registry, GitHub Action, or CI supply-chain compromise.

Code enforces bearer authentication on protected routers, active-user checks,
active-organization membership, route-specific roles, tenant object checks,
audit-header rejection, loopback Compose publication, non-root containers,
read-only roots, dropped capabilities, and `no-new-privileges`. TLS, trusted
hosts/proxies, forwarded-header policy, network ACLs, durable secret management,
body limits, distributed rate limiting, database backup/encryption, and public
health/metrics restriction are deployment assumptions, not code-enforced here.

## Route and authorization inventory

The generator:

```text
python scripts/security/inventory_routes.py --output docs/security/evidence/route-inventory.md
```

imports the actual FastAPI application, flattens FastAPI 0.140 included-router
wrappers, traverses dependency graphs, applies a reviewed route-local role map,
and fails if an application route is unmapped or a policy entry is stale.

Totals are:

| Authorization class | Method/path entries |
|---|---:|
| Public | 16 |
| Authenticated only | 3 |
| Tenant member | 6 |
| Tenant manager | 11 |
| Tenant administrator | 1 |

The 37 total includes GET and HEAD for four framework documentation/schema
paths. There are 29 application method/path entries. Full identifiers, data
effects, dependency chains, existing tests, and missing negatives are in the
linked evidence file.

## Authentication and session testing

Passing negative cases include missing bearer credentials, non-bearer schemes,
malformed JWTs, invalid signatures, expired tokens, manipulated algorithm
headers, missing/malformed/nonexistent subjects, inactive/deleted user handling,
client-supplied audit identity headers, and malformed request identifiers.
Responses were 400/401 as designed and did not contain a traceback or signing
value. Login returns the same generic error for missing/inactive users and wrong
passwords. The in-process lockout triggers after five failures for five minutes.

Results and limitations:

- **Fail, A87-001 / #106:** a refresh token is accepted as an access token.
- **Fail, A87-005 / #110:** no refresh endpoint, rotation/reuse detection,
  persisted session revocation, or API logout exists.
- Access tokens cannot be presented to a refresh endpoint because no such
  endpoint exists; this is blocked rather than a pass.
- Streamlit logout clears local session/result state but cannot invalidate a
  server token.
- Direct local execution generates an ephemeral high-entropy signing key and
  warns; Compose fails closed unless a persistent key is supplied.
- The lockout store is process-local memory, resets on restart, is keyed by
  normalized username, and is not a distributed public-deployment control.

## Tenant isolation and authorization

Executed tests cover a valid member, no membership, another organization,
member/admin management flags, cross-organization account and staged-transaction
identifiers, organization-scoped idempotency keys, tenant-scoped audit reads,
report budget scope, cache keys, and Streamlit stale-result clearing on failure,
login change, and logout.

No cross-tenant financial-data read or write was demonstrated. Other-tenant
objects return 403 or a scope-hiding 404 as designed. Organizations have active
state and inactive organizations are rejected; memberships have no active-state
field, so inactive-membership testing is not applicable to the current model.

**A87-002 / #107:** `/market/sync` and `/tax/sync` resolve provider selection
before organization authorization. Strict expected-failure tests confirm the
ordering gap. FX authorization occurs before provider discovery and is the
reference order.

Audit success attribution is tested. The application does not define a complete
policy requiring persisted audit entries for every denial, so denial-log
coverage remains a limitation.

## Input, upload, error, and output safety

Validated controls include positive organization identifiers on key routes,
date-order checks, bounded audit pagination, transaction balancing, cross-tenant
account rejection before staging, malformed JSON/TOML/UTF-8 plan errors, strict
plan defaults, tax JSONLogic shape/operator validation, and generic UI/API error
rendering that removes credential-like keys.

Open results:

- **A87-003 / #108:** budget CSV text cells preserve `=`, `+`, `-`, and `@`
  formula prefixes.
- **A87-004 / #109:** expensive forecast, scenario, and workflow collections;
  nested metadata; request bodies; and Streamlit uploads lack application-level
  maxima. Streamlit holds whole uploads in session memory.
- Market symbols and several free-text/provider values have inconsistent length
  and normalization bounds.
- Standard JSON parsing accepts duplicate keys with last-value semantics; no
  security policy documents this behavior.
- Upload filenames are retained only as display/parser hints and are not used as
  server filesystem paths, so traversal was not demonstrated.
- Duplicate CSV-header behavior and spreadsheet-specific export interoperability
  remain untested.
- Nonfinite numeric values are constrained where Pydantic/Decimal conversion
  rejects them, but comprehensive extremes across every forecast/provider path
  remain incomplete.

## Persistence, transaction, concurrency, and audit integrity

The 52 required accounting-control tests and focused suite cover balanced
posting, rollback on partial failures, snapshot isolation, tax synchronization
rollback and stale deletion scope, workflow retry/idempotency, organization
namespacing, concurrent scheduler lifecycle calls, per-plan commit/rollback,
cache tenant keys, and report failure behavior. No integrity failure was
demonstrated.

Limitations:

- no real multi-process database load test was run;
- SQLite is the tested persistence engine;
- API-level concurrent duplicate posting and stale-session races are not fully
  exercised;
- audit records have read-only API exposure, but direct database operators can
  modify them and no append-only/tamper-evident store is implemented;
- scheduler shutdown uses `wait=False`, so operator shutdown semantics depend on
  APScheduler and process termination timing.

## Provider and background-task boundaries

Provider keys map through an operator-controlled allowlist; loader interface and
capability checks reject arbitrary caller module names. The operator can
configure/import Python modules, which is trusted-code execution by design.
Background FX backfill uses isolated sessions and a trusted actor copied after
authorization. Scheduler jobs create their own session, roll back failed plans,
and continue other plans.

External requests use HTTPS and ECB/OpenExchangeRates set 20-second timeouts.
No application response-size limit exists, retries are inconsistent, and the
yfinance adapter does not expose an explicit timeout in this code. Malformed
upstream payload coverage is partial. These resilience gaps contribute to
A87-004 and block public-deployment approval. No live credential or production
endpoint test was used.

## Full-history secret scan

```text
gitleaks git . --log-opts="--all" --redact --report-format json \
  --report-path C:\tmp\app-accounting-modular-gitleaks-165eb3a.json
```

- tool: Gitleaks 8.30.1;
- range: `--all`, 227 commits;
- data scanned: approximately 2.38 MB;
- result: **PASS**, zero findings;
- reviewed false positives: none because the report was empty;
- real credentials found: none;
- raw report: temporary host storage only;
- raw report SHA-256:
  `37517E5F3DC66819F61F5A7BB8ACE1921282415F10551D2DEFA5C3EB0985B570`.

No revocation action is required from this scan.

## Static analysis

```text
C:\tmp\app-accounting-audit-165eb3a\Scripts\python.exe \
  -m bandit -r src -f json \
  -o C:\tmp\app-accounting-modular-bandit-165eb3a.json
```

Bandit 1.9.4 reported 18 Low findings: B101 (5), B105/B106 string heuristics
(3), B110/B112 best-effort exception handling (6), and B404/B603 subprocess
imports/calls (4). Every result was manually reviewed:

- asserts guard initialized internal worker/model state and do not authorize a
  request;
- `bearer` and client session-state key names are not passwords;
- swallowed exceptions are cleanup, optional dependency, metrics fallback, or
  invalid-model candidate paths;
- subprocess arguments in audit/quality developer tools are fixed internal
  command sequences with `shell=False`.

No Bandit result is actionable security remediation. Raw report SHA-256:
`D8C9A5F1BFE606EA859DF734B013F58815F6EB3C751CEF6682C548F7D4DC53D8`.
Semgrep was unavailable and was not claimed as run.

## Dependencies, supply chain, and GitHub configuration

Authoritative isolated commands:

```text
python -m pip check
python -m pip_audit -r requirements.txt -r requirements-dev.txt
```

Both passed; pip-audit 2.10.1 found no known vulnerabilities. Runtime and
development requirements have lower/upper bounds; Ruff alone is exactly pinned
at 0.15.21, but the repository does not state its pin rationale. Optional
provider dependencies are installed in the shared runtime manifest rather than
separately locked extras.

All three Actions references are full 40-character SHAs. Workflow permissions
are `contents: read`, checkout uses `persist-credentials: false`, untrusted PRs
use `pull_request` rather than `pull_request_target`, and evidence retention is
14 days. The repository Actions policy allows selected GitHub-owned/verified
Actions and reports SHA pinning required.

Read-only GitHub checks recorded:

- public repository; default branch `main`;
- active `Protect main` ruleset: deletion/non-fast-forward protection, linear
  history, pull requests, resolved review threads, strict required checks for
  `container-smoke` and builds on Python 3.12/3.13/3.14;
- legacy branch-protection endpoint returns 404 because the ruleset is the
  active protection mechanism;
- Dependabot security updates enabled and zero open Dependabot alerts;
- secret scanning and push protection enabled; zero open secret alerts;
- non-provider pattern scanning and validity checks disabled;
- private vulnerability reporting enabled;
- code-scanning query reported no analysis; CodeQL/SAST hosted coverage is not
  established.

**A87-006 / #111:** mutable base-image tags and unlocked, unhashed dependency
resolution make future container builds non-reproducible.

## SBOM

```text
python -m pip_audit --timeout 60 \
  -r requirements.txt -r requirements-dev.txt \
  --format cyclonedx-json \
  --output C:\tmp\app-accounting-modular-sbom-165eb3a.cdx.json
```

Result: **PASS with limitations**. The CycloneDX 1.4 JSON contains 121 resolved
components and zero vulnerability records. It includes names/versions but no
component hashes, licenses, or PURLs. The raw temporary SBOM contains no
credential values but is not committed because it represents this host's one
non-reproducible resolution. SHA-256:
`C931C2F2F5494173619666722EA16CF79CB92FA8418D507BF453F13DF8665029`.
Image SBOMs are blocked until Docker or Syft is available.

## Dynamic API, browser, proxy, and container evidence

A TestClient procedure with an in-memory database found:

- untrusted `Host` accepted with 200;
- CORS preflight returned 405 and no allow-origin header;
- HSTS, CSP, `X-Content-Type-Options`, and `X-Frame-Options` were absent.

This does not create cross-origin permission, but confirms that trusted-host,
TLS/HSTS, forwarded-header, CSP, and proxy policies are not code-enforced.
They are required operator/reverse-proxy controls. Direct API authentication was
tested independently of Streamlit.

Static tests pass for Compose fail-closed JWT interpolation, loopback-only
published ports, UID/GID 10001, read-only roots, dropped capabilities,
`no-new-privileges`, `/data` and bounded `/tmp` write paths, and CI teardown.

Local runtime validation is **blocked** because Docker/Compose are not installed.
No container was started or exposed. API/Streamlit live health, actual runtime
UID/GID, filesystem writes, capability state, image SBOM, shutdown, and volume
cleanup require exact-head hosted `container-smoke` evidence.

## Findings register

| ID | Severity | Title | Evidence | Compensating control | Release effect | Issue |
|---|---|---|---|---|---|---|
| A87-001 | High | Refresh token accepted as access token | Sanitized in-memory proof and strict xfail | Tenant roles still enforced; loopback mode limits exposure | Blocks every release-ready claim | [#106](https://github.com/Nobodyworld/app-accounting-modular/issues/106) |
| A87-002 | Medium | Provider discovery precedes tenant authorization | Market/tax strict xfails | Authentication required; data write still follows authorization | Remediate/accept before broader deployment | [#107](https://github.com/Nobodyworld/app-accounting-modular/issues/107) |
| A87-003 | Medium | CSV formula injection | Four prefix proofs/strict xfails | Authenticated export; no automatic opening | Remediate/accept before broader deployment | [#108](https://github.com/Nobodyworld/app-accounting-modular/issues/108) |
| A87-004 | Medium | Unbounded expensive inputs and uploads | Schema review and strict xfails | Authentication and loopback Compose | Blocks LAN/public approval | [#109](https://github.com/Nobodyworld/app-accounting-modular/issues/109) |
| A87-005 | Medium | No session revocation or refresh rotation | Route/state review | Active-user check; short access default; key rotation | Blocks complete session-security conclusion | [#110](https://github.com/Nobodyworld/app-accounting-modular/issues/110) |
| A87-006 | Medium | Non-reproducible container supply chain | Dockerfiles/manifests/SBOM review | Dependabot, SHA-pinned Actions, clean current audit | Blocks production-like container approval | [#111](https://github.com/Nobodyworld/app-accounting-modular/issues/111) |

No Critical finding was identified. One High and five Medium findings remain
open. Broad remediation is intentionally not mixed into audit PR #105.

## Deployment disposition

| Deployment mode | Decision | Required controls / unresolved assumptions |
|---|---|---|
| Local demonstration | **Conditional nonproduction use only; not a release approval** | Loopback binding, generated nonproduction data/identities, explicit Compose key when containers are used, no sensitive uploads, open findings understood |
| Trusted-team workstation | **Not approved** | A87-001 and session lifecycle must be resolved; host access, secret storage, backups, data retention, upload/input limits required |
| LAN deployment | **Blocked** | All open High/Medium findings, TLS, trusted hosts/proxies, firewall/network ACL, distributed rate limiting, durable sessions/secrets, monitoring |
| Reverse-proxied containers | **Blocked** | All open High/Medium findings, exact-head runtime evidence, pinned images/dependencies, proxy/header/body limits, HTTPS, production data controls |
| Public hosting | **Blocked** | No public-hosting security model or completed dynamic/pentest evidence; public diagnostic surfaces and all operator controls require disposition |

## Unresolved limitations and required follow-up

- Docker/Compose/image SBOM and live container checks are locally blocked.
- Exact-head hosted CI must finish and be linked after the audit commit is pushed.
- Semgrep, Syft, and CodeQL/code-scanning evidence are absent.
- No multi-process/distributed rate-limit, concurrency, or production database
  exercise was performed.
- Request/response byte limits, nested-depth limits, duplicate-key policy,
  provider response limits, and complete malformed-provider cases remain open.
- TLS, trusted proxy/host, security headers, network ACL, database encryption,
  backup/restore, log access/retention, and secret rotation are operator controls
  without runtime evidence in this audit.
- GitHub secret validity/non-provider scanning is disabled; the owner must decide
  whether to enable them.
- The audit remains open until finding disposition and owner approval are
  recorded. A green CI run alone is insufficient.

## Final sign-off

- Audit application SHA confirmed: **yes**
- Audit branch starting SHA confirmed: **yes**
- Evidence complete and reproducible: **no; limitations above**
- Critical findings open: **0**
- High findings open: **1**
- Medium findings open: **5**
- Documentation updated: **in progress**
- Release/deployment statement approved by owner: **no**
- PR #105 draft and unmerged: **must be reverified after push**
- Issue #87 open: **must be reverified after push**

This report must remain **In progress**. It does not declare the repository
release-ready.
