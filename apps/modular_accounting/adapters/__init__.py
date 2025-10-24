"""Infrastructure adapters for modular data sources."""

from ..domain.ports import CommodityDataPort, FXDataPort, TaxDataPort
from .base import CommodityDataAdapter, FXDataAdapter, TaxDataAdapter
from .in_memory import (
    InMemoryCommodityAdapter,
    InMemoryFXAdapter,
    InMemoryTaxAdapter,
)

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
