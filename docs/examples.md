# Examples

## Produce a Snapshot with Custom Symbols
```bash
python -m cli.demo_cli snapshot --base EUR --commodity XAU --commodity XPT
```

## Filter Tax Rules by Jurisdiction
```bash
python -m cli.demo_cli snapshot --jurisdiction uk
```

## Embed the Service in Python Code
```python
from datetime import date
from decimal import Decimal

from apps.modular_accounting.adapters import InMemoryCommodityAdapter, InMemoryFXAdapter, InMemoryTaxAdapter
from apps.modular_accounting.application import DataSnapshotService, SnapshotRequest
from apps.modular_accounting.domain import TaxRule

fx = InMemoryFXAdapter({"USD": Decimal("1.08")})
commodities = InMemoryCommodityAdapter({"XAU": Decimal("2029.12")}, currency="EUR")
taxes = InMemoryTaxAdapter([
    TaxRule("eu", Decimal("0.21"), "EU VAT", effective_from=date(2024, 1, 1)),
])

service = DataSnapshotService(fx, commodities, taxes)
request = SnapshotRequest(
    base_currency="EUR",
    commodity_symbols=["XAU"],
    jurisdictions=None,
)
snapshot = service.create_snapshot(request)
```
