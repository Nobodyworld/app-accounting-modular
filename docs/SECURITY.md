# Security Policy

## Supported Versions

| Version | Supported |
| --- | --- |
| `main` | Best-effort Early Beta support |
| Tagged releases | None published |

## Reporting a Vulnerability

Use the repository's **Security** tab and select **Report a vulnerability** to submit a private report through GitHub Private Vulnerability Reporting.

Include reproduction steps, an impact assessment, affected versions or commits, and proof-of-concept material when it can be shared safely. Do not include vulnerability details in a public issue, pull request, discussion, or commit.

Response and remediation timing depends on severity, reproducibility, maintainer availability, and the scope of the Early Beta. No fixed response-time or remediation-time guarantee is provided.

## Coordinated Disclosure

- Keep the report private until a fix, mitigation, or disclosure plan is agreed.
- Security advisories may be coordinated and published through GitHub Security Advisories.
- Reporter credit may be provided with consent.
- Avoid accessing, modifying, or retaining data that is not necessary to demonstrate the issue.

## Validated Deployment Boundary

The default Docker Compose profile is for local demonstration only.

- Host ports are bound explicitly to `127.0.0.1`.
- Compose requires the caller to provide `MODACCT_JWT_SECRET_KEY`; the repository does not ship a fallback signing key.
- A copied `.env.example` intentionally leaves the signing secret empty so startup fails until a real secret is generated.
- API and web processes run as numeric UID/GID `10001:10001` rather than root.
- Both root filesystems are read-only, all Linux capabilities are dropped, and `no-new-privileges` is enabled.
- The API may write only to its `/data` volume and the bounded `/tmp` tmpfs; the web service may write only to its bounded `/tmp` tmpfs.
- Both images use the same official Python 3.14 manifest-list digest and install
  the complete runtime graph from `requirements-container.lock` with required
  hashes, binary wheels only, dependency resolution disabled, and `pip check`.
- Container builds retain the pip version supplied by the pinned base; they do
  not upgrade pip, setuptools, or wheel.
- Container-internal listeners remain available for API/web service-to-service communication, but that does not authorize LAN or public exposure.
- FastAPI rejects request bodies over the configured maximum before route execution; every proxy or ingress must enforce an equal or smaller cap.
- Budget and scenario-plan files are constrained by both Streamlit configuration and the stricter application upload policy.

Do not publish the API or Streamlit ports on `0.0.0.0`, a LAN address, or a public interface without a separate review covering HTTPS termination, trusted proxies and hosts, network access control, production secret management, host/container runtime hardening, and the residual operator assumptions in the [post-UX security audit](security/POST_UX_PRE_RELEASE_AUDIT.md).

The application may generate an ephemeral JWT secret for direct temporary local API demonstrations. That mode rotates sessions on restart and is not a substitute for an explicit persistent secret in containers or any production-like deployment.

## Authentication Session Lifecycle

Successful password authentication creates an `AuthSession` row through the existing SQLModel `create_all` lifecycle. The row contains a random session identifier, user reference, SHA-256 digest of the currently valid refresh-token `jti`, refresh/session expiration, creation and last-rotation timestamps, a rotation counter, and optional bounded revocation metadata. Access tokens, refresh tokens, passwords, authorization headers, token payloads, raw IP addresses, and user-agent fingerprints are never stored in this table.

Every newly issued access and refresh JWT contains only `sub`, `sid`, `jti`, `type`, `iat`, and `exp`. An access token is accepted only while its referenced persisted session exists, belongs to the subject user, is unexpired and unrevoked, and the user remains active. The API returns the same generic credential error for invalid claims, missing sessions, revoked or expired sessions, and inactive users.

`POST /auth/refresh` consumes a refresh token once. Rotation conditionally replaces the stored digest only when the session identifier, current digest, unrevoked state, and expiration still match. A stale but otherwise valid refresh token is treated as reuse and revokes the complete session, including any access and refresh tokens issued by the preceding successful rotation. Session revocation is available through current-session logout and an organization-scoped administrator route; the administrator must belong to and administer the organization, and target users outside that tenant are reported as not found.

Expired session rows are removed in bounded batches opportunistically during login and refresh and by the hourly `auth-session-cleanup` APScheduler job. Active unexpired rows, including revoked rows retained for deterministic revocation evidence, are not removed.

Streamlit keeps access, refresh, and session identifiers only in in-memory session state. Refresh credentials are private state: they are not rendered, logged, placed in URLs, written to disk, or included in downloads. Protected requests may perform one refresh and one retry after a `401`; refresh failure clears local authentication state. Logout attempts server revocation first and always clears local authentication and protected-result state, even when the API is unavailable.

## Hardening Checklist

- Rotate API keys and secrets regularly; never commit secrets to the repository.
- Generate a stable high-entropy `MODACCT_JWT_SECRET_KEY` before Docker Compose startup.
- Preserve explicit loopback host-port bindings for the local Compose profile.
- Preserve the non-root `10001:10001` runtime, read-only root filesystems, capability drops, and `no-new-privileges` controls.
- Restrict API persistence to `/data` and temporary runtime writes to `/tmp`.
- Run `pre-commit run --all-files` for formatting and static checks.
- Run `python -m src.tools.secret_scan` for the repository's lightweight current-tree secret pattern check.
- Before public release, run Gitleaks or an equivalent full-history scanner and record the tool version, command, commits scanned, findings, false-positive disposition, and final result in [`../PUBLIC_RELEASE_AUDIT.md`](../PUBLIC_RELEASE_AUDIT.md).
- Use environment variables (see `config/.env.example`) to configure sensitive settings.
- Review [`DEPENDENCIES.md`](DEPENDENCIES.md) quarterly for updated security posture notes and dependency audit status.
- Run `python scripts/dependencies/verify_container_lock.py` for offline lock
  freshness and policy validation. Regenerate only as an intentional,
  networked dependency update and review every direct and transitive change.
- Verify downloaded image evidence checksums before using
  `gh attestation verify`; pull-request evidence is intentionally unattested,
  while publication is restricted to trusted `main` pushes and manual runs.
- Audit startup failure logs for sensitive payloads; `StartupManager` surfaces exception metadata for diagnostics, so ensure startup steps raise errors without embedding secrets or personal data.
- Preserve the centralized inbound request, collection, metadata, and upload limits documented in [`resource-limits.md`](resource-limits.md).

## Accountant close trust boundary

The `/close` surface inherits persisted access/refresh session separation and trusted audit attribution. Clients provide organization and resource identifiers but never trusted actor identifiers. Tenant membership is resolved before tenant-scoped object lookup; missing or cross-tenant close resources use the same nondisclosing `404` result. Ledger managers may create a default-policy cycle and prepare controls. Only administrators may record a typed, bounded, reasoned policy override or not-applicable exception; arbitrary policy metadata is rejected and never exported. Administrator-only final close, reopen, cancellation, and revocation preserve explicit separation of duties.

The posting lock is enforced in `period_lock.py` from both direct and staged workflow paths. A no-op tenant-period update obtains the validated SQLite writer position before period state is checked, serializing close against posting; `auto_process=true` uses one transaction so rejection removes newly staged rows too. `READY_FOR_APPROVAL` rejects posting with stable code `ACCOUNTING_PERIOD_CLOSE_READY` until administrator return-to-work; `CLOSED` rejects with `ACCOUNTING_PERIOD_CLOSED`. Successful in-period posting advances `AccountingPeriod.ledger_activity_revision` atomically with the journal. Period boundaries are inclusive, and create/reopen acquire the tenant gate before checking every inclusive overlap pattern. Journal requestors cannot approve their own request, reconciliation preparers cannot provide final approval, and assignment IDs must resolve to active same-tenant members.

Lifecycle writes are guarded in services: ready freezes operational records and posting, closed and cancelled are read-only, and administrator return-to-work/restart/reopen require bounded reasons. Atomic version and content-revision compare-and-swap updates prevent two sessions from both succeeding. Reconciliations and variance runs record the ledger revision they reviewed; readiness accepts only the current revision and only the latest variance run's rows. Evidence freshness requires both `CloseCycle.content_revision` and the period ledger revision. Draft persistence conditionally locks/verifies cycle status and both revisions. Final close, audit records, and final `CLOSED` evidence commit atomically.

Evidence is assembled in memory under hard row and archive-byte limits. Only manifest metadata is persisted. Evidence records and their own audit rows are outside the explicit snapshot cutoff, preventing manifest self-reference; the returned/downloaded bytes, persisted evidence metadata, and generation audit therefore use one hash. The archive excludes JWTs, passwords, credentials, environment dumps, host paths, unrestricted provider metadata, exception traces, and raw uploads. CSV text is neutralized through the existing spreadsheet-safety helper. The feature-specific review and remaining assumptions are recorded in [`security/V0_2_CLOSE_WORKSPACE_SECURITY_REVIEW.md`](security/V0_2_CLOSE_WORKSPACE_SECURITY_REVIEW.md); it does not rewrite or broaden the historical baseline audit.

### Outbound provider trust boundary

The network-backed provider inventory is limited to ECB, OpenExchangeRates, and
YFinance. Direct FX HTTPS reads use a shared 1 MiB streaming byte cap, declared
`Content-Length` validation, independent byte counting, a 512-rate record cap,
5-second connect and 20-second read timeouts, and at most two attempts for
connection/read failures or HTTP 429, 502, 503, and 504. Other 4xx responses,
oversized bodies, and invalid payloads are not retried.

Provider failures use stable domain exceptions and sanitized structured logs.
Response bodies, credentials, authorization headers, request parameter
dictionaries, credential-bearing URLs, and raw upstream exception messages are
excluded. OpenExchangeRates credentials remain request parameters and are never
interpolated into URL strings or diagnostics. Tests use deterministic stubs and
no live provider credentials or network requests.

### Provider catalog governance trust boundary

Provider governance persistence is a narrowing control plane. Only keys and modules in the current process-level `settings.allowed_providers` configuration can reach the v0.3 conformance loader; database rows contain safe fingerprints and metadata but no executable module/factory path. Tenant API models reject additional registration fields and cannot install packages, discover a registry, or create trusted registrations. A removed allowlist key is historical and non-executable even if organization policy or defaults still reference it. Drifted registrations are quarantined until an operator explicitly reconciles reviewed process configuration.

Provider-backed routes authenticate a persisted session and authorize organization membership/role before governance discovery, conformance inspection, provider construction, or data operations. Explicit and default selection require current process trust, persisted identity agreement, structural conformance, API compatibility, capability match, and organization enablement. Defaults that cease to satisfy those conditions become ineffective rather than silently falling back to the disabled key.

Policy and default writes use organization-scoped revision comparison, trusted actor identity, atomic governance/audit commit, rollback on failure, and cache invalidation only after commit. Cross-tenant identifiers return nondisclosing responses. Credential readiness exposes only manifest-declared variable names and presence booleans; values are never stored, hashed, logged, placed in errors/URLs, or included in deterministic governance evidence. Presence is configuration readiness, not remote credential validation.

YFinance is restricted to one application-level download call, `threads=False`,
a 20-second timeout, a maximum 10,000-day requested range, and 10,000 returned
rows. Because its high-level API returns an already materialized DataFrame, the
application cannot independently stream or byte-count the library's internal
HTTP response.

These outbound controls are separate from the inbound request/upload limits and
from the container dependency, evidence, and trusted-attestation controls in
the [container supply-chain guide](container-supply-chain.md).
