# Provider Catalog Governance Architecture

Status: implemented v0.4 contract for issue #145; release acceptance remains subject to exact-head validation.

## Purpose

The v0.3 provider SDK establishes a structural contract for trusted provider modules. Issue #145 adds the operational layer that is still missing: persistent organization policy, deterministic default selection, bounded readiness/conformance evidence, and administrator-facing controls.

In v0.5 the same contract implementation is delivered by the standalone
`modular_accounting_provider_sdk` package; `apps.provider_sdk` re-exports it.
An installed external wheel, package metadata, or entry point contributes no
process trust. Governance reconciliation still begins only from the operator's
current `settings.allowed_providers` identity.

The v0.5 acceptance harness executes this transition against disposable SQLite
state: rejection before import, exact `ProviderInfo` allowlisting, conformance,
safe registration, administrator enable/default mutation, governed resolution,
process-trust removal, retained historical evidence, and non-executability.
Tenant policy schemas reject packages, wheels, URLs, modules, factories, entry
points, and manifests as self-authorization inputs.

This design deliberately separates **code trust** from **tenant policy**.

- Code/process configuration decides which Python provider modules are trusted enough to be considered loadable.
- The provider SDK/conformance layer proves that a trusted module has the expected manifest, capability shape, factory contract, and API-major compatibility.
- Persistence may remember registration evidence and organization policy, but it may never create a new executable trust relationship by itself.
- Organization policy may narrow the trusted catalog, select defaults, and record governance state. It may not add arbitrary Python modules or install packages.

This preserves the post-audit authorization and provider-loading boundaries while making provider administration durable.

## Non-negotiable trust boundary

A provider is eligible for runtime resolution only when all of the following are true:

1. its key exists in the current process-level `settings.allowed_providers` allowlist;
2. the configured module passes the existing provider SDK/conformance boundary for that key and declared capabilities;
3. persisted registration evidence, when present, does not conflict with the current process-level key/module/capability contract;
4. the current organization policy permits the provider;
5. the provider is not quarantined or otherwise blocked by authoritative governance state;
6. the provider is compatible with the current application API under the existing compatibility policy; and
7. any route-specific tenant authorization has already succeeded before provider resolution begins.

Persistence is therefore a **narrowing control plane**, not a second allowlist that can broaden executable code.

## Implemented layers

```text
┌───────────────────────────────────────────────────────────────────────┐
│ Process / operator trust configuration                               │
│ settings.allowed_providers                                           │
│ - trusted key                                                        │
│ - trusted Python module                                              │
│ - expected capabilities                                              │
└───────────────────────────────┬───────────────────────────────────────┘
                                │ only trusted candidates
                                ▼
┌───────────────────────────────────────────────────────────────────────┐
│ v0.3 SDK + conformance boundary                                      │
│ ProviderManifest / inspect_provider_module / load_conforming_provider │
│ - key/capability alignment                                           │
│ - factory/method/signature checks                                    │
│ - API-major compatibility                                            │
│ - sanitized deterministic evidence                                   │
└───────────────────────────────┬───────────────────────────────────────┘
                                │ reconciled safe metadata
                                ▼
┌───────────────────────────────────────────────────────────────────────┐
│ Persistent provider governance                                      │
│ - trusted-registration snapshot/reference                            │
│ - organization provider policy                                      │
│ - organization default by capability                                │
│ - revision/CAS                                                       │
│ - timestamps and audit references                                   │
│ - no credentials                                                     │
└───────────────────────────────┬───────────────────────────────────────┘
                                │ effective policy
                                ▼
┌───────────────────────────────────────────────────────────────────────┐
│ Provider governance service / resolver                              │
│ - authorize first                                                    │
│ - intersect process trust with persisted organization policy         │
│ - resolve explicit/default provider deterministically                │
│ - surface bounded readiness/conformance evidence                     │
│ - invalidate revision-aware caches                                   │
└───────────────────────┬──────────────────────────┬────────────────────┘
                        │                          │
                        ▼                          ▼
              FastAPI `/providers`       Protected tenant API paths
              + governance workspace     FX / market / tax / snapshot / ...
```

The public/local Streamlit **Snapshot Review** is deliberately outside that tenant-policy path. It derives a safe selector from current process-trusted provider descriptors, filters for structural conformance and compatibility, and constructs the selected provider through the existing allowlist/conformance loader. It does not call `/providers`, read persisted organization policy/defaults, or claim tenant-governed selection. Signing in unlocks protected workspaces but does not change Snapshot Review semantics.

## Persistent model responsibilities

The implementation uses three separate SQLModel tables and preserves their distinct responsibilities.

- `TrustedProviderRegistration` stores bounded configuration/manifest fingerprints, capabilities, provider/SDK/API versions, conformance/compatibility and lifecycle state, revision, and UTC reconciliation timestamps. It stores no importable module path.
- `OrganizationProviderPolicy` is unique on organization/provider, records explicit enablement, a bounded note, revision, timestamps, actor, and audit reference.
- `OrganizationCapabilityDefault` is unique on organization/capability and records the selected provider plus revision, timestamps, actor, and audit reference.

`ProviderGovernanceService` is the authoritative intersection of those rows with the current process allowlist and the v0.3 conformance loader. Runtime fallback is the lexicographically first effective provider key after an explicit request and a valid organization default have been considered. Invalid persisted defaults remain visible as ineffective evidence but are never executed.

### Trusted provider registration

A durable registration record may cache safe evidence for a provider already trusted by process configuration. It should be keyed by the provider's existing namespaced key and contain only bounded metadata required to detect drift and explain governance state.

Candidate fields include:

- provider key;
- trusted module identity or a stable fingerprint derived from the current trusted configuration;
- declared capability set;
- provider/SDK/API version metadata;
- manifest fingerprint or deterministic serialized-manifest hash;
- conformance status/codes;
- lifecycle state such as active or quarantined when needed;
- revision;
- deterministic UTC reconciliation timestamps.

A persisted module path must never be sufficient to import a provider. Runtime code must always resolve the module from the current process-level trusted configuration.

### Organization provider policy

Organization policy records which already-trusted providers are usable for one organization.

Candidate fields include:

- organization ID;
- provider key;
- enabled flag or explicit policy state;
- bounded administrator note/reason;
- revision;
- created/updated UTC timestamps;
- trusted actor/audit reference.

The unique key should prevent duplicate policy rows for the same organization/provider pair.

### Organization capability default

Where several trusted providers implement one capability, an organization may select one effective default.

Candidate fields include:

- organization ID;
- capability;
- provider key;
- revision;
- created/updated UTC timestamps;
- trusted actor/audit reference.

A default is valid only while the selected provider remains process-trusted, conforming, compatible, capability-matched, and enabled for that organization.

## Bootstrap and reconciliation

The current `DEFAULT_ALLOWED_PROVIDERS` / `settings.allowed_providers` configuration remains the operator trust source.

A reconciliation operation should:

1. take a deterministic snapshot of the current trusted configuration;
2. inspect each configured provider through the v0.3 structural conformance path without invoking provider data/network methods;
3. compare safe manifest/configuration identity with persisted registration evidence;
4. insert or update safe registration metadata idempotently;
5. mark drift or incompatibility explicitly rather than silently accepting it;
6. ensure a provider removed from current process configuration can no longer be resolved, even if historical rows remain for audit/reference purposes;
7. invalidate governance/provider caches only after a successful transaction; and
8. produce deterministic human-readable/JSON reconciliation evidence.

A tenant-facing API must not accept a module path, factory path, package name, wheel, URL, or arbitrary import string as a way to create a trusted registration.

## Runtime resolution contract

Provider-backed routes currently authorize the organization before calling the provider loader. Issue #145 must preserve that ordering.

The preferred flow is:

1. authenticate the persisted session;
2. authorize organization membership and route-specific role;
3. resolve explicit or default provider policy for the authorized organization;
4. verify the selected key still exists in the process trust allowlist;
5. verify current conformance/compatibility and organization enablement;
6. load through the existing conformance-aware provider loader;
7. execute the bounded provider/application service operation; and
8. record provenance including the effective provider key and relevant governance revision/evidence identifiers.

Policy lookup must not move provider discovery ahead of tenant authorization.

## Default selection

Default provider selection should be deterministic and server-derived.

Priority should be explicit and documented, for example:

1. a caller-supplied provider key, when the route permits explicit selection and the key is effective for the organization;
2. the organization's valid persisted default for that capability; then
3. a deterministic repository-defined fallback among trusted/enabled providers when the product contract permits fallback.

If no valid provider exists, fail with a stable bounded domain error. Do not silently activate a disabled provider or fall back to a process-trusted provider that organization policy explicitly blocks.

The implementation should choose one precise fallback contract and test it; the architecture must not leave fallback order dependent on dictionary/import order.

## Credential readiness

Provider manifests may declare credential environment-variable names. Governance may report whether those variables are present, but it must not expose their values.

Safe output:

```json
{
  "credential_requirements": [
    {"name": "EXAMPLE_API_KEY", "present": true}
  ],
  "configured": true
}
```

Forbidden behavior includes:

- returning the value;
- persisting the value;
- logging the value;
- hashing it for later equality checks;
- exporting it in governance evidence; or
- embedding it in errors/URLs.

Credential presence is configuration readiness, not proof that a remote credential is valid.

## Conformance, compatibility, and health

The governance surface should distinguish separate concepts rather than collapse them into one green/red status:

- **trusted**: present in current process allowlist;
- **conforming**: passes v0.3 structural conformance;
- **compatible**: passes the current API/provider compatibility policy;
- **enabled**: permitted by organization policy;
- **credential-ready**: required environment variables are present;
- **operational health/freshness**: bounded evidence from an existing safe health contract, when available.

Structural conformance remains hermetic and network-free. Live provider health must never become a required hermetic-test dependency or a production-certification claim.

## API boundary

The new API should be cohesive under `/providers` or an equivalent dedicated prefix.

Expected responsibilities include:

- list safe trusted catalog/effective state for an authorized organization;
- get one provider's safe governance/conformance detail;
- list organization policies/defaults;
- update enablement/policy using revision protection;
- set/clear capability defaults using revision protection;
- report credential readiness as booleans only;
- preview/export deterministic governance evidence.

Read operations may be available to organization members when useful for provenance. Policy mutations require organization administrator authority unless an existing narrower role is explicitly justified by the product contract.

Global/operator trust changes should remain CLI/local configuration work unless the repository first introduces a separately reviewed global-administrator security model.

## Streamlit boundary

The Provider Governance workspace should render API-derived state and must not independently recompute provider eligibility.

Provider Governance is authenticated and organization-scoped. By contrast, Snapshot Review remains a public/local controlled demonstration backed only by current process trust and the local `SnapshotOrchestrator`. Anonymous users cannot inspect tenant governance state, and the local selector does not expose organization defaults. Authenticated tenant `/snapshot` requests remain governed by the server-side organization resolver; they are a separate path from the public Streamlit workflow.

The UI should prioritize:

- effective status and why;
- capability/default role;
- conformance/compatibility summary;
- credential readiness without values;
- provenance/source;
- administrative next action;
- revision conflict guidance;
- collapsed sanitized technical detail.

All provider-governance tenant state must be cleared with the same logout, failed-authentication, session-replacement, and organization-transition boundaries used by the existing protected workspaces.

## Audit and concurrency

Every organization policy/default mutation should:

- use trusted authenticated actor identity;
- verify tenant scope before object lookup/mutation;
- perform revision/CAS validation;
- commit the policy change and its bounded audit evidence transactionally;
- roll back fully on error; and
- invalidate caches only after successful commit.

Cross-tenant identifiers should not reveal whether a protected policy row exists.

## Evidence export

Provider-governance evidence should be deterministic and secret-free. A snapshot may contain:

- organization ID;
- effective provider keys/capabilities/defaults;
- trusted/configuration fingerprints that reveal no secrets;
- manifest/conformance/compatibility summaries;
- enablement/quarantine state;
- credential names and presence booleans only;
- revisions/timestamps;
- audit references;
- source/application version metadata;
- SHA-256 manifest if multiple files are bundled.

Do not include raw environment values, filesystem paths, unrestricted exceptions, access/refresh tokens, authorization headers, provider credentials, or raw upstream response bodies.

## Migration and startup considerations

Issue #145 should not silently turn the repository into a migration-platform rewrite. The implementation may use the current SQLModel schema bootstrap pattern when consistent with repository policy, but the new tables and startup behavior must be deterministic and tested.

If implementation reveals that safe provider-governance persistence requires a broader Alembic/database-migration tranche, record that as a separate issue unless it is a hard blocker to this product outcome.

Startup must not become dependent on live provider networks. Structural catalog reconciliation may run without external I/O; any operational health probe must remain bounded and separately controlled.

## Required security regressions

Tests must prove at least:

- a persisted arbitrary module path cannot become executable;
- a process-allowlist removal overrides stale persisted registration state;
- manifest key/capability drift fails closed;
- organization policy cannot enable a provider outside the trusted process set;
- disabled/quarantined providers cannot be selected through an explicit request or default;
- tenant authorization happens before provider discovery/resolution;
- cross-tenant identifiers remain nondisclosing;
- credentials never appear in API responses, logs, persistence, or exported evidence;
- stale revisions reject concurrent policy mutation;
- failed writes roll back policy and audit state atomically;
- cache invalidation reflects committed state and not failed transactions; and
- required tests perform no live network access.

## Scope boundary

This architecture does not authorize:

- a provider marketplace or certification program;
- remote package discovery/installation;
- tenant-supplied module/factory paths;
- arbitrary dynamic imports from persistence;
- secret storage;
- public-hosting approval;
- live bank-reconciliation claims;
- production tax/market/bank certification; or
- a broad frontend rewrite.

Those require separate product/security decisions.
