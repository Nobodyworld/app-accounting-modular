"""Deprecated service facade maintained for backward compatibility."""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any

warnings.warn(
    "apps.modular_accounting.services is deprecated; "
    "use apps.modular_accounting.application instead.",
    DeprecationWarning,
    stacklevel=2,
)

if TYPE_CHECKING:  # pragma: no cover - import only for static typing
    from ..application import DataSnapshot, DataSnapshotService, SnapshotRequest

__all__ = ["DataSnapshot", "DataSnapshotService", "SnapshotRequest"]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(name)
    from ..application import DataSnapshot, DataSnapshotService, SnapshotRequest

    mapping = {
        "DataSnapshot": DataSnapshot,
        "DataSnapshotService": DataSnapshotService,
        "SnapshotRequest": SnapshotRequest,
    }
    return mapping[name]
