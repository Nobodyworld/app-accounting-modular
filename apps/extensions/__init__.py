"""Extension scaffolding for modular integrations beyond data providers."""

from .registry import (
    ExtensionManifest,
    ExtensionRegistry,
    extension_registry,
    load_extension_module,
    load_extensions,
)

__all__ = [
    "ExtensionManifest",
    "ExtensionRegistry",
    "extension_registry",
    "load_extension_module",
    "load_extensions",
]
