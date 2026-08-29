"""Compatibility re-exports for standalone structural conformance."""

from modular_accounting_provider_sdk.conformance import (
    ConformanceCheck,
    ConformingProvider,
    ProviderConformanceError,
    ProviderConformanceReport,
    inspect_provider_module,
    load_conforming_provider,
)

__all__ = [
    "ConformanceCheck",
    "ConformingProvider",
    "ProviderConformanceError",
    "ProviderConformanceReport",
    "inspect_provider_module",
    "load_conforming_provider",
]
