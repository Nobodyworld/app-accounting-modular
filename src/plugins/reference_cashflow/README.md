# Cashflow Analytics Extension

Demonstration extension generated for Stage 3 to showcase the new scaffolding
and tracing primitives. Enable it via the configuration key
`reporting:cashflow` to expose:

- A health probe surfaced on `/health/ready` reporting synthetic variance
  calculations.
- A cache gauge (`cashflow_projection`) to highlight instrumentation from
  extension modules.
- Span creation via `apps.observability.tracing.traced` during registration so
  extension activation is visible in traces and logs.

Regenerate similar extensions using `macli scaffold-extension`.
