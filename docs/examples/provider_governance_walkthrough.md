# Provider Governance Controlled Walkthrough

This walkthrough demonstrates the v0.4 governance boundary in a local **Early Beta / Portfolio Preview** environment. It does not validate external credentials, certify providers, install packages, or authorize LAN/public deployment.

## 1. Reconcile operator trust

Configure only reviewed providers in `settings.allowed_providers`, initialize the database, and run:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m cli.macli provider-sdk governance-reconcile --format table
python -m cli.macli provider-sdk governance-validate --format table
```

The reconcile command structurally inspects current configured modules without calling provider data methods. New trusted keys are recorded as safe registration evidence. Identity drift is quarantined; use `--accept-drift` only after reviewing the changed process configuration and manifest. Removing a key from process configuration makes historical persistence non-executable immediately.

## 2. Review as a member

Start FastAPI and Streamlit, sign in through **API Session**, select an organization, and open **Provider Governance**. A member can review trusted/effective state, capabilities, defaults, provider/SDK versions, compatibility, conformance, credential-variable presence, provenance, and next action. Technical details are collapsed by default.

Credential presence means only that the named environment variable is non-empty. Values are never rendered, persisted, logged, hashed, or exported, and readiness is not remote credential validation.

## 3. Administer policy

Sign in as an organization administrator. Enable or disable an already-trusted provider with its current policy revision, or set/clear a capability default with the current default revision. Successful writes show explicit confirmation. A stale revision returns a deterministic conflict and instructs the administrator to refresh; the server never silently overwrites newer policy.

Tenant input cannot add module/factory paths. Disabling a provider or invalidating its default affects subsequent explicit and default FX, market, tax, and snapshot resolution.

## 4. Export evidence

Use the protected API preview/export or the operator CLI:

```powershell
python -m cli.macli provider-sdk governance-export --organization-id 1 --format json
```

The deterministic JSON includes policies, defaults, safe fingerprints, conformance/compatibility summaries, credential variable names with booleans, revisions, timestamps, audit references, versions, and an evidence SHA-256. It excludes secrets, environment values, authorization headers, filesystem paths, raw upstream bodies, and unrestricted exceptions.

## 5. Session boundaries

Verify that provider-governance tenant state disappears on logout, failed authentication, session replacement, and organization change. Repeat the UI review at desktop, tablet, narrow-mobile, and literal 200% browser zoom; use keyboard traversal and confirm a visible focus indicator. The validated deployment boundary remains local demonstration.
