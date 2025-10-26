# Agent Operations Guide

This repository is agent-friendly. Follow these guardrails when automating
changes:

1. **Bootstrap observability** – call `apps.observability.tracing.configure_tracing`
   when running bespoke scripts so trace IDs propagate into logs.
2. **Use the Makefile** – `make ci` mirrors the full lint/type/test/security
   suite, while `make health` runs runtime probes. Run them before handing work
   back to humans.
3. **Generate extensions via CLI** – prefer `macli scaffold-extension` over
   manual file creation to ensure tracing and health hooks are present.
4. **Respect TODO tags** – new TODOs must use the `[priority][estimate]` format
   (e.g. `# TODO[P2][1d]: backfill forecast tracing`).
5. **Document intent** – update `ARCHITECTURE_OVERVIEW.md` and `STEWARDS_REPORT.md`
   when altering cross-cutting concerns (observability, extension contracts,
   release tooling).

These conventions keep human and AI contributors aligned and auditable.
