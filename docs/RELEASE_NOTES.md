# Release Notes

## Current Candidate

Version file: `0.1.0`  
Validated baseline before the current release-readiness pull request: `b00b2d84d082e8d97ee9dba0cf366c1fbe6f21e1`

This repository is being prepared as a public accounting-controls portfolio project. It demonstrates modular snapshot orchestration, provider provenance, journal controls, health diagnostics, scenario plans, CLI/API/Streamlit review surfaces, and extension contracts. It is not presented as a production ERP, tax engine, treasury system, or regulated bank-feed product.

## Highlights

- Accountant-first Streamlit review flow for financial snapshots, source evidence, freshness, journal-control status, and diagnostics.
- Provider-swappable FX, commodity, tax, market, macroeconomic, and bank-feed demonstration adapters.
- Balanced journal-control examples and account traceability.
- Deterministic CLI and API diagnostics for health, telemetry, scenario plans, and extension contracts.
- Prometheus-compatible metrics, request tracing, startup diagnostics, and scheduler health reporting.
- Apache-2.0 licensing with `NOTICE`, contribution guidance, security policy, and public-release evidence.
- README-linked screenshots, architecture overview, accounting-control workflow, and accounting case studies.

## Latest Public-readiness Work

- PR #54 cleaned the README-linked workflow and architecture SVG connector geometry.
- Hosted CI run `28931509566` passed the Python 3.12, 3.13, and 3.14 matrix, including the quality gate, accounting-control suites, and artifact upload.
- PR #52 replaced `python-jose` with `PyJWT[crypto]`, removing the vulnerable transitive `ecdsa` dependency path identified by `pip-audit`.
- The current release-readiness pass refreshes the public audit, roadmap, setup instructions, container configuration, and CI container smoke coverage.

## Validation

The quality gate runs:

- Ruff linting and formatting checks;
- targeted mypy validation;
- full pytest with an aggregate 85% coverage floor;
- focused accounting-control tests;
- `pip check`;
- `pip-audit`; and
- current-tree secret scanning.

Recorded release evidence also includes documentation link validation, focused Streamlit regression tests, and a full-history Gitleaks scan with no findings. See [`../PUBLIC_RELEASE_AUDIT.md`](../PUBLIC_RELEASE_AUDIT.md) for the current release assessment.

## Running the Demonstration

Use [`setup.md`](setup.md) for the supported local and container workflows. The primary review surfaces are:

- FastAPI service and OpenAPI documentation;
- Streamlit demonstration interface; and
- `cli.macli` operational commands.

Demo providers use controlled sample data unless external credentials are configured.

## Known Limits

- This is a portfolio-grade controls toolkit, not a production accounting system.
- The React directory is experimental and is not part of the validated runtime.
- OTLP export remains optional and requires the OpenTelemetry extras described in the operations documentation.
- Streamlit `use_container_width` deprecation warnings remain a maintenance item.
- Provider catalog persistence and several legacy TODOs remain future work.
- Repository-level settings such as visibility, branch protection, security features, topics, and social preview require owner review in GitHub.

## Release Decision

The repository should remain private until the current release-readiness pull request passes hosted CI and the owner completes the manual checks listed in [`../PUBLIC_RELEASE_AUDIT.md`](../PUBLIC_RELEASE_AUDIT.md).
