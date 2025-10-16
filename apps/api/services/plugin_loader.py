import importlib
import pkgutil
from typing import Any

def available_plugins(package: str = "plugins") -> list[str]:
    try:
        pkg = importlib.import_module(package)
    except ModuleNotFoundError:
        return []
    return [m.name for m in pkgutil.iter_modules(pkg.__path__) if not m.ispkg]

def load_provider(module_path: str, factory: str = "provider") -> Any:
    mod = importlib.import_module(module_path)
    if not hasattr(mod, factory):
        raise ValueError(f"Factory '{factory}' not found in {module_path}")
    return getattr(mod, factory)()
