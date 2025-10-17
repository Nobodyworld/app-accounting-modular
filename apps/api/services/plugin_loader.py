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
    except (ModuleNotFoundError, ImportError):
        return []

    if not hasattr(pkg, "__path__"):
        return []

    modules: set[str] = set()
    prefix = f"{pkg.__name__}."
    for module_info in pkgutil.walk_packages(pkg.__path__, prefix=prefix):
        if module_info.ispkg:
            continue
        modules.add(module_info.name)

    return sorted(modules)


def load_provider(module_path: str, factory: str = "provider") -> Any:
    """Load and instantiate a provider from ``module_path``."""

    if not module_path:
        raise ValueError("Module path is required")

    try:
        mod = importlib.import_module(module_path)
    except (ModuleNotFoundError, ImportError) as exc:
        raise ValueError(f"Unable to import provider module '{module_path}'") from exc

    if not hasattr(mod, factory):
        raise ValueError(f"Factory '{factory}' not found in {module_path}")
    factory_fn = getattr(mod, factory)
    if not callable(factory_fn):  # pragma: no cover - defensive
        raise ValueError(f"Factory '{factory}' in {module_path} is not callable")

    provider = factory_fn()
    if provider is None:
        raise ValueError(f"Factory '{factory}' in {module_path} returned None")
    return provider
