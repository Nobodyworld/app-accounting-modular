# Examples

## Produce a Snapshot with Custom Symbols
```bash
python -m cli.demo_cli snapshot --base EUR --commodity XAU --commodity XPT --format table --include-diagnostics
```

## Filter Tax Rules by Jurisdiction
```bash
python -m cli.demo_cli snapshot --jurisdiction uk --format json --include-diagnostics
```

## Embed the Service in Python Code
```python
from datetime import date
from decimal import Decimal

from apps.modular_accounting.adapters import InMemoryCommodityAdapter, InMemoryFXAdapter, InMemoryTaxAdapter
from apps.modular_accounting.application import (
    DataSnapshotService,
    SnapshotRequest,
)
from apps.modular_accounting.domain import TaxRule

fx = InMemoryFXAdapter({"USD": Decimal("1.08")})
commodities = InMemoryCommodityAdapter({"XAU": Decimal("2029.12")}, currency="EUR")
taxes = InMemoryTaxAdapter([
    TaxRule("eu", Decimal("0.21"), "EU VAT", effective_from=date(2024, 1, 1)),
])

# Positional arguments
service = DataSnapshotService(fx, commodities, taxes)
request = SnapshotRequest(
    base_currency="EUR",
    commodity_symbols=["XAU"],
    jurisdictions=None,
)
snapshot = service.create_snapshot(request)

# Keyword arguments (legacy names)
service = DataSnapshotService(
    fx_adapter=fx,
    commodity_adapter=commodities,
    tax_adapter=taxes,
)

# Keyword arguments (port names) with cache tuning
service = DataSnapshotService(
    fx_port=fx,
    commodity_port=commodities,
    tax_port=taxes,
    default_cache_ttl=300,  # expire cached data every five minutes
)

snapshot = service.build_snapshot(base_currency="EUR", commodity_symbols=["XAU"])

# Cached results can be reused within the same process
snapshot_again = service.create_snapshot(request)
assert snapshot_again.fx_rates is snapshot.fx_rates  # tuple identity preserved

# Cache statistics and invalidation hooks are exposed for observability
stats = service.cache_stats()
assert stats["fx"].hits >= 1
service.clear_cache()
```

## Inspect platform health
```bash
python -m cli.macli health
```

## List configured extensions
```bash
python -m cli.macli extensions
```

## Build provider-backed data snapshots
```bash
python -m cli.macli snapshot --base USD --commodity XAU --jurisdiction US --format json
```
The command returns a JSON payload containing FX rates, commodity quotes, tax rules, cache statistics, and the provider keys
used for each capability. Switch to `--format table` for a human-friendly summary when demonstrating the workflow.
## Execute batch scenario plans
```bash
python -m cli.macli snapshot-scenarios --plan docs/examples/scenario-plan.json --format table
```
The command parses a JSON or TOML plan, reuses the configured providers for each scenario, and prints an aggregated summary
alongside per-scenario diagnostics. Use the companion HTTP endpoint to automate the same workflow:
```bash
curl -X POST http://localhost:8000/snapshot/scenarios \
  -H "Content-Type: application/json" \
  -d @docs/examples/scenario-plan.json
```
