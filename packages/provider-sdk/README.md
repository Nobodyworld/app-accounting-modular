# Modular Accounting Provider SDK

This is the installable, zero-runtime-dependency author kit for the Modular
Accounting **Early Beta / Portfolio Preview**. It provides immutable provider
contracts, structural conformance, standalone project scaffolding, deterministic
artifact evidence, and a standard-library CLI.

Installing this SDK or an authored provider does not authorize provider execution.
The local-demonstration application loads only exact modules named in its
operator-controlled allowlist, after tenant authorization and v0.4 governance
checks. There is no marketplace, registry discovery, certification, package
publication, or production-provider support.

Use:

```console
python -m modular_accounting_provider_sdk scaffold demo:sample --capability market
python -m modular_accounting_provider_sdk validate demo_sample.provider --api-version 0.5.0
```

Structural validation imports the requested module but does not invoke its factory
or provider data methods unless `--instantiate` is explicitly supplied.

