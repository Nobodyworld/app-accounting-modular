# Modular Accounting Provider SDK

This is the installable, zero-runtime-dependency author kit for the Modular
Accounting **Early Beta / Portfolio Preview**. It provides immutable provider
contracts, structural conformance, standalone project scaffolding, deterministic
artifact evidence, and a standard-library CLI.

The SDK declares its own zero-dependency backend through
`backend-path = ["src"]`. The standard frontend is authoritative:

```console
python -m build --no-isolation packages/provider-sdk
```

The resulting sdist retains `src/modular_accounting_provider_sdk`, package
metadata, README, LICENSE, SECURITY guidance, typing marker, and the in-tree
backend needed for an offline rebuild. Generated providers declare
`modular-accounting-provider-sdk==0.5.0` as both their runtime dependency and
their PEP 517 build-system requirement. Repository acceptance installs both
wheel and sdist variants with `PIP_NO_INDEX=1` and validates every wheel RECORD
hash and size.

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
