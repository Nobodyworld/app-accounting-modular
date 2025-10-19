"""Database models used by the Modular Accounting API."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "Account",
    "AccountType",
    "AuditAction",
    "AuditLog",
    "Budget",
    "BudgetLine",
    "Country",
    "Event",
    "ForecastOutput",
    "ForecastPlan",
    "Instrument",
    "JournalEntry",
    "Membership",
    "Organization",
    "Price",
    "Rate",
    "StagedPosting",
    "StagedTransaction",
    "TaxRule",
    "Transaction",
    "User",
    "WorkflowStatus",
]

_MODELS_MODULE: Any | None = None


def _load_models_module() -> Any:
    global _MODELS_MODULE
    if _MODELS_MODULE is None:
        _MODELS_MODULE = import_module("apps.api.models.models")
    return _MODELS_MODULE


def __getattr__(name: str) -> Any:
    if name in __all__:
        module = _load_models_module()
        value = getattr(module, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module 'apps.api.models' has no attribute '{name}'")


def __dir__() -> list[str]:
    return sorted(__all__)
