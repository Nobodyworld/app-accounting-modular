"""OECD VAT reference data provider stub package."""

from __future__ import annotations

from .provider import OECDFakeTaxProvider, provider

OECDFallbackTaxProvider = OECDFakeTaxProvider

__all__ = [
    "OECDFakeTaxProvider",
    "OECDFallbackTaxProvider",
    "provider",
]

# TODO - (plugins) Remove legacy alias once downstream references migrate.
