"""Deprecated wrapper forwarding to the application snapshot service."""

from __future__ import annotations

import warnings

from ..application.snapshots import DataSnapshot, DataSnapshotService, SnapshotRequest

warnings.warn(
    "apps.modular_accounting.services.snapshot is deprecated; "
    "import from apps.modular_accounting.application instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["DataSnapshot", "DataSnapshotService", "SnapshotRequest"]
