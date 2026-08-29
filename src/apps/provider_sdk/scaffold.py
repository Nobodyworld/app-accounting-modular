"""Compatibility re-exports for standalone provider scaffolding."""

from modular_accounting_provider_sdk.scaffold import (
    ProviderProjectScaffold,
    ProviderScaffold,
    normalise_distribution_name,
    normalise_provider_package,
    scaffold_project,
    scaffold_provider,
)

__all__ = [
    "ProviderProjectScaffold",
    "ProviderScaffold",
    "normalise_distribution_name",
    "normalise_provider_package",
    "scaffold_project",
    "scaffold_provider",
]
