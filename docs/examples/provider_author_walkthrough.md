# Controlled External Provider Author Walkthrough

This walkthrough is for the local **Early Beta / Portfolio Preview** boundary.
It publishes nothing and provides no marketplace, certification, production
provider, credential, or public/LAN deployment claim.

1. Run `python scripts/provider_author_acceptance.py --output provider-author-acceptance.json`.
2. Confirm `python -m build --no-isolation` used the SDK's declared in-tree backend and inspect the path-free SDK wheel/sdist names, sizes, inventories, and SHA-256 hashes.
3. Confirm separate fresh environments installed the local SDK wheel and SDK sdist with no repository `PYTHONPATH`, no index access, no runtime dependencies, and no importable `apps` package.
4. Confirm the standalone CLI generated `pyproject.toml`, `README.md`, `src/<package>/`, `py.typed`, and `tests/test_conformance.py`.
5. Confirm the generated project declared the exact SDK build-system requirement, its wheel/sdist were built twice through that backend, both preserved matching metadata and `src/` layout, and separate consumer environments installed each artifact.
6. Confirm generated tests and structural JSON conformance passed while socket connections were denied and the factory/data methods remained deferred.
7. Confirm the application rejected the importable key without importing its module before it appeared in `settings.allowed_providers`.
8. Inspect the observed exact key/module/capability allowlist, runtime conformance, safe v0.4 registration, administrator authorization, revisioned enable/default changes, and governed resolution results.
9. Confirm tenant policy inputs rejected package, wheel, URL, module, factory, entry-point, and manifest self-authorization fields.
10. Confirm process-trust removal marked historical evidence removed and made explicit/default resolution non-executable.

The harness removes all disposable venv and build state in a `finally` boundary.
Its JSON contains no absolute paths, environment values, credentials, tokens,
provider bodies, tenant data, or unrestricted exception messages.
