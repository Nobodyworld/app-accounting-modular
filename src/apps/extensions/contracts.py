"""Contracts advertised by extensions for automation and modular growth."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = ["ExtensionContract"]


@dataclass(slots=True, frozen=True)
class ExtensionContract:
    """Immutable description of an extension-provided contract surface."""

    kind: str
    name: str
    version: str = "1.0"
    description: str | None = None
    entrypoint: str | None = None
    input_schema: dict[str, Any] | None = field(default=None, repr=False)
    output_schema: dict[str, Any] | None = field(default=None, repr=False)
    tags: tuple[str, ...] = ()

    def serialise(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation of the contract."""

        return {
            "kind": self.kind,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "entrypoint": self.entrypoint,
            "tags": list(self.tags),
            "input_schema": self.input_schema or {},
            "output_schema": self.output_schema or {},
        }
