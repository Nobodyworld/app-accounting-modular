"""Adapter interfaces and utilities for modular data sources."""

from .base import CommodityDataAdapter, FXDataAdapter, TaxDataAdapter
from .in_memory import (
    InMemoryCommodityAdapter,
    InMemoryFXAdapter,
    InMemoryTaxAdapter,
)

__all__ = [
    "CommodityDataAdapter",
    "FXDataAdapter",
    "TaxDataAdapter",
    "InMemoryCommodityAdapter",
    "InMemoryFXAdapter",
    "InMemoryTaxAdapter",
]
