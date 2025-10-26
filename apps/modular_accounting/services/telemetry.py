"""Deprecated telemetry facade preserved for backwards compatibility."""

from __future__ import annotations

import warnings
from typing import Any

warnings.warn(
    "apps.modular_accounting.services.telemetry is deprecated; "
    "import from apps.modular_accounting.application.telemetry instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["SnapshotTelemetry", "telemetry_provider"]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(name)
    from ..application.telemetry import SnapshotTelemetry, telemetry_provider

    mapping = {
        "SnapshotTelemetry": SnapshotTelemetry,
        "telemetry_provider": telemetry_provider,
    }
    return mapping[name]
