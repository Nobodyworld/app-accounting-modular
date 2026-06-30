"""Service layer helpers for the Modular Accounting API."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = [
    "BudgetService",
    "ForecastService",
    "FXService",
    "LedgerService",
    "MarketService",
    "ProviderHandle",
    "ProviderMetadata",
    "active_extensions",
    "TaxService",
    "WorkflowService",
    "available_providers",
    "load_configured_extensions",
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
    "active_extensions": ("apps.api.services.extension_loader", "active_extensions"),
    "TaxService": ("apps.api.services.tax_service", "TaxService"),
    "WorkflowService": ("apps.api.services.workflow_service", "WorkflowService"),
    "available_providers": ("apps.api.services.plugin_loader", "available_providers"),
    "load_configured_extensions": (
        "apps.api.services.extension_loader",
        "load_configured_extensions",
    ),
    "load_provider": ("apps.api.services.plugin_loader", "load_provider"),
}

if TYPE_CHECKING:  # pragma: no cover - for static analyzers
    from .budget_service import BudgetService
    from .extension_loader import active_extensions, load_configured_extensions
    from .forecast_service import ForecastService
    from .fx_service import FXService
    from .ledger_service import LedgerService
    from .market_service import MarketService
    from .plugin_loader import ProviderHandle, ProviderMetadata, available_providers, load_provider
    from .tax_service import TaxService
    from .workflow_service import WorkflowService
else:
    BudgetService = ForecastService = FXService = LedgerService = MarketService = None  # type: ignore[assignment]
    ProviderHandle = ProviderMetadata = available_providers = load_provider = None  # type: ignore[assignment]
    active_extensions = load_configured_extensions = TaxService = WorkflowService = None  # type: ignore[assignment]


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module 'apps.api.services' has no attribute '{name}'") from exc
    module = import_module(module_name)
    value = getattr(module, attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
