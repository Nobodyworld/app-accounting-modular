"""Extension scaffolding for modular integrations beyond data providers."""

from .contracts import ExtensionContract
from .registry import (
    ExtensionManifest,
    ExtensionRegistry,
    extension_registry,
    load_extension_module,
    load_extensions,
)
from .scaffold import ExtensionScaffold, normalise_package_name, scaffold_extension

__all__ = [
    "ExtensionContract",
    "ExtensionManifest",
    "ExtensionRegistry",
    "extension_registry",
    "load_extension_module",
    "load_extensions",
    "ExtensionScaffold",
    "normalise_package_name",
    "scaffold_extension",
]
