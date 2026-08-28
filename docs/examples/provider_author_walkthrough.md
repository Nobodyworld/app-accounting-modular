# Controlled External Provider Author Walkthrough

This walkthrough is for the local **Early Beta / Portfolio Preview** boundary.
It publishes nothing and provides no marketplace, certification, production
provider, credential, or public/LAN deployment claim.

1. Run `python scripts/provider_author_acceptance.py --output provider-author-acceptance.json`.
2. Inspect the path-free SDK wheel/sdist names, sizes, inventories, and SHA-256 hashes.
3. Confirm the author venv installed only the local SDK wheel with no repository `PYTHONPATH` and could not import `apps`.
4. Confirm the standalone CLI generated `pyproject.toml`, `README.md`, `src/<package>/`, `py.typed`, and `tests/test_conformance.py`.
5. Confirm the generated wheel/sdist were built twice with matching hashes and installed beside the SDK in a separate consumer venv.
6. Confirm generated tests and structural JSON conformance passed while socket connections were denied and the factory/data methods remained deferred.
7. Confirm the application rejected the importable key before it appeared in `settings.allowed_providers`.
8. For an intentionally reviewed provider, configure the exact key/module/capabilities, run application-side validation and v0.4 governance reconciliation, then enable/default it through organization policy.
9. Remove the process allowlist entry to prove historical persistence can no longer execute it.

The harness removes all disposable venv and build state in a `finally` boundary.
Its JSON contains no absolute paths, environment values, credentials, tokens,
provider bodies, tenant data, or unrestricted exception messages.
