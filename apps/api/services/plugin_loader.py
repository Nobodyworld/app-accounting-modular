from __future__ import annotations

import importlib
import pkgutil
from typing import Any


def available_plugins(package: str = "plugins") -> list[str]:
    """Return a sorted list of importable plugin module names for the package."""

    try:
        pkg = importlib.import_module(package)
    except ModuleNotFoundError:
        return []

    names: list[str] = []
    for module in pkgutil.iter_modules(pkg.__path__):
        full_name = f"{package}.{module.name}"
        if module.ispkg:
            provider_name = f"{full_name}.provider"
            try:
                importlib.import_module(provider_name)
            except ModuleNotFoundError:
                names.append(full_name)
            else:
                names.append(provider_name)
        else:
            names.append(full_name)
    return sorted(names)


def load_provider(module_path: str, factory: str = "provider") -> Any:
    """Load a provider instance via a module-level factory."""

    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as exc:
        raise ValueError(f"Module '{module_path}' could not be imported") from exc

    try:
        factory_obj = getattr(module, factory)
    except AttributeError as exc:
        raise ValueError(f"Factory '{factory}' not found in {module_path}") from exc

    if not callable(factory_obj):
        raise ValueError(f"Factory '{factory}' in {module_path} is not callable")

    provider = factory_obj()
    if provider is None:
        raise ValueError(f"Factory '{factory}' in {module_path} returned None")
    return provider
