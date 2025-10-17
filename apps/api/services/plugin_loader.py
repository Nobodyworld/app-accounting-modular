"""Plugin discovery and loading helpers."""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any

__all__ = ["available_plugins", "load_provider"]


def available_plugins(package: str = "plugins") -> list[str]:
    """Return a sorted list of provider plugin module names."""

    try:
        pkg = importlib.import_module(package)
    except ModuleNotFoundError:
        return []
    return sorted(m.name for m in pkgutil.iter_modules(pkg.__path__) if not m.ispkg)


def load_provider(module_path: str, factory: str = "provider") -> Any:
    """Load and instantiate a provider from ``module_path``."""

    mod = importlib.import_module(module_path)
    if not hasattr(mod, factory):
        raise ValueError(f"Factory '{factory}' not found in {module_path}")
    factory_fn = getattr(mod, factory)
    if not callable(factory_fn):  # pragma: no cover - defensive
        raise ValueError(f"Factory '{factory}' in {module_path} is not callable")
    return factory_fn()
