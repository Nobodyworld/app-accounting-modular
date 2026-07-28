"""Reusable validation for JSON-compatible inbound metadata."""

from __future__ import annotations

from collections.abc import Mapping

from .limits import (
    MAX_METADATA_DEPTH,
    MAX_METADATA_KEYS_PER_MAPPING,
    MAX_METADATA_STRING_LENGTH,
    MAX_METADATA_TOTAL_NODES,
)


def validate_metadata(value: object) -> object:
    """Validate metadata iteratively without changing the submitted value.

    Depth starts at zero for the root container. Nodes include every scalar and
    container value; mapping keys are validated as strings but are not counted
    separately from their associated values.
    """

    stack: list[tuple[object, int]] = [(value, 0)]
    nodes = 0

    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_METADATA_TOTAL_NODES:
            raise ValueError(f"metadata must contain at most {MAX_METADATA_TOTAL_NODES} nodes")
        if depth > MAX_METADATA_DEPTH:
            raise ValueError(f"metadata nesting depth must not exceed {MAX_METADATA_DEPTH}")

        if current is None or isinstance(current, bool | int | float):
            continue
        if isinstance(current, str):
            if len(current) > MAX_METADATA_STRING_LENGTH:
                raise ValueError(f"metadata strings must contain at most {MAX_METADATA_STRING_LENGTH} characters")
            continue
        if isinstance(current, Mapping):
            if len(current) > MAX_METADATA_KEYS_PER_MAPPING:
                raise ValueError(f"metadata mappings must contain at most {MAX_METADATA_KEYS_PER_MAPPING} keys")
            for key, child in current.items():
                if not isinstance(key, str):
                    raise ValueError("metadata mapping keys must be strings")
                if len(key) > MAX_METADATA_STRING_LENGTH:
                    raise ValueError(f"metadata strings must contain at most {MAX_METADATA_STRING_LENGTH} characters")
                stack.append((child, depth + 1))
            continue
        if isinstance(current, list):
            stack.extend((child, depth + 1) for child in current)
            continue
        raise ValueError("metadata values must be JSON-compatible scalars, lists, or mappings")

    return value
