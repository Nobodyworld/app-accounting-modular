"""Deprecated adapter aliases maintained for backward compatibility."""

from __future__ import annotations

import warnings

from ..domain.ports import CommodityDataPort, FXDataPort, TaxDataPort

warnings.warn(
    "apps.modular_accounting.adapters.base is deprecated; " "import ports from apps.modular_accounting.domain instead.",
    DeprecationWarning,
    stacklevel=2,
)

FXDataAdapter = FXDataPort
CommodityDataAdapter = CommodityDataPort
TaxDataAdapter = TaxDataPort

__all__ = [
    "CommodityDataAdapter",
    "FXDataAdapter",
    "TaxDataAdapter",
]
