"""Deprecated service facade maintained for backward compatibility."""

from __future__ import annotations

import warnings

from ..application import DataSnapshot, DataSnapshotService, SnapshotRequest

warnings.warn(
    "apps.modular_accounting.services is deprecated; "
    "use apps.modular_accounting.application instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["DataSnapshot", "DataSnapshotService", "SnapshotRequest"]
