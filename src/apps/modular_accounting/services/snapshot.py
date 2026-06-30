"""Deprecated wrapper forwarding to the application snapshot service."""

from __future__ import annotations

import warnings

from ..application import snapshots as _snapshots

warnings.warn(
    "apps.modular_accounting.services.snapshot is deprecated; import from apps.modular_accounting.application instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["DataSnapshot", "DataSnapshotService", "SnapshotRequest"]

DataSnapshot = _snapshots.DataSnapshot
DataSnapshotService = _snapshots.DataSnapshotService
SnapshotRequest = _snapshots.SnapshotRequest
