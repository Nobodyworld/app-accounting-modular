"""Deprecated telemetry facade preserved for backwards compatibility."""

from __future__ import annotations

import warnings

from ..application.telemetry import SnapshotTelemetry, telemetry_provider

warnings.warn(
    "apps.modular_accounting.services.telemetry is deprecated; "
    "import from apps.modular_accounting.application.telemetry instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["SnapshotTelemetry", "telemetry_provider"]
