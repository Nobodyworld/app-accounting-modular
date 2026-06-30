"""API routers exposed by the Modular Accounting service.

This module imports and exposes the commonly-used router submodules so that
consumers can do `from apps.api import routers; routers.core` or
`from apps.api.routers import core as core_router` without relying on the
package importer to have already loaded submodules. Import errors are caught
and the attribute is set to `None` so import-time failures are non-fatal.
"""

import types
from importlib import import_module

__all__: list[str] = [
    "audit",
    "auth",
    "core",
    "forecast",
    "fx",
    "health",
    "extensions",
    "ledger",
    "market",
    "snapshot",
    "reports",
    "tax",
    "workflow",
]

# Try to import each listed submodule and expose it as an attribute on the
# package. If a submodule fails to import (for example because optional
# third-party deps are not installed), set the attribute to None instead of
# raising so downstream static/runtime checks can handle it gracefully.
for _name in __all__:
    try:
        _mod: types.ModuleType | None = import_module(f"{__name__}.{_name}")
    except Exception:
        _mod = None
    globals()[_name] = _mod
