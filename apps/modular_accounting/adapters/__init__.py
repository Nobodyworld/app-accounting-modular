"""Infrastructure adapters for modular data sources."""

from ..domain.ports import CommodityDataPort, FXDataPort, TaxDataPort
from .in_memory import (
    InMemoryCommodityAdapter,
    InMemoryFXAdapter,
    InMemoryTaxAdapter,
)

# Backwards compatible aliases retained for integrations that still import the
# historical ``*Adapter`` symbols.  Importing from ``domain.ports`` keeps the
# definitions local and avoids triggering the deprecated ``adapters.base``
# module, eliminating deprecation warnings during normal use.
FXDataAdapter = FXDataPort
CommodityDataAdapter = CommodityDataPort
TaxDataAdapter = TaxDataPort

__all__ = [
    "CommodityDataAdapter",
    "CommodityDataPort",
    "FXDataAdapter",
    "FXDataPort",
    "InMemoryCommodityAdapter",
    "InMemoryFXAdapter",
    "InMemoryTaxAdapter",
    "TaxDataAdapter",
    "TaxDataPort",
]
