"""Service layer helpers for the Modular Accounting API."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "BudgetService",
    "ForecastService",
    "FXService",
    "LedgerService",
    "MarketService",
    "ProviderHandle",
    "ProviderMetadata",
    "TaxService",
    "WorkflowService",
    "available_providers",
    "load_provider",
]

_EXPORTS: dict[str, tuple[str, str]] = {
    "BudgetService": ("apps.api.services.budget_service", "BudgetService"),
    "ForecastService": ("apps.api.services.forecast_service", "ForecastService"),
    "FXService": ("apps.api.services.fx_service", "FXService"),
    "LedgerService": ("apps.api.services.ledger_service", "LedgerService"),
    "MarketService": ("apps.api.services.market_service", "MarketService"),
    "ProviderHandle": ("apps.api.services.plugin_loader", "ProviderHandle"),
    "ProviderMetadata": ("apps.api.services.plugin_loader", "ProviderMetadata"),
    "TaxService": ("apps.api.services.tax_service", "TaxService"),
    "WorkflowService": ("apps.api.services.workflow_service", "WorkflowService"),
    "available_providers": ("apps.api.services.plugin_loader", "available_providers"),
    "load_provider": ("apps.api.services.plugin_loader", "load_provider"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(
            f"module 'apps.api.services' has no attribute '{name}'"
        ) from exc
    module = import_module(module_name)
    value = getattr(module, attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
