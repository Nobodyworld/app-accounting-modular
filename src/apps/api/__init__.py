"""FastAPI backend for Modular Accounting."""

from .config import Settings, get_settings, settings

__all__ = [
    "Settings",
    "get_settings",
    "settings",
]
