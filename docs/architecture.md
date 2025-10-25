# Architecture Overview

Modular Accounting follows a layered architecture that isolates domain
behaviour from infrastructure concerns. The goal is to keep integrations
composable while retaining testability.

```
┌─────────────────────┐
│ Interfaces          │  CLI commands, APIs, background jobs
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│ Application Layer   │  `DataSnapshotService`, `SnapshotRequest`, `TTLCache`
│  • normalises input │  • caches adapter calls with TTL + metrics
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│ Domain Ports        │  `FXDataPort`, `CommodityDataPort`, `TaxDataPort`
│  • runtime checks   │  • typed models (`FXRate`, `CommodityQuote`, `TaxRule`)
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│ Infrastructure      │  In-memory adapters, future provider SDKs
└─────────────────────┘
```

## Snapshot lifecycle

1. Callers assemble a `SnapshotRequest` (or pass primitives to
   `DataSnapshotService.build_snapshot`). Inputs are trimmed, upper-cased, and
   deduplicated so adapters never see redundant work.
2. The service fetches FX rates, commodity quotes, and tax rules from the
   configured ports. Results are cached in-memory by request scope using
   thread-safe TTL caches so repeated calls reuse data until entries expire.
3. A `DataSnapshot` object is returned, bundling the immutable results for
   downstream processing, rendering, or persistence.

## Extension points

- Implement new adapters by satisfying the domain ports in
  `apps/modular_accounting/domain/ports.py`. The runtime-checkable protocols
  make it easy to validate implementations in tests.
- Swap adapters at service construction time to integrate real APIs, cached
  stores, or streaming data feeds without modifying orchestration logic. Cache
  duration can be tuned per port (or turned off entirely) via the
  ``DataSnapshotService`` constructor parameters.
- Build higher-level workflows (e.g., reconciliation or hedging) by composing
  the application service inside FastAPI routes, Celery tasks, or CLI commands.
