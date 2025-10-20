"""Utilities for normalising metadata payloads passed across API boundaries."""

from __future__ import annotations

import re
from collections.abc import Mapping, MutableMapping, Sequence
from datetime import datetime, timezone
from typing import Any


_SNAKE_CASE_PATTERN = re.compile(r"(?<!^)(?=[A-Z])")


def _normalise_key(key: str) -> str:
    """Return a consistent snake_case representation for ``key``."""

    lowered = key.replace("-", "_").replace(" ", "_")
    snake = _SNAKE_CASE_PATTERN.sub("_", lowered).lower()
    snake = re.sub(r"__+", "_", snake)
    return snake.strip("_")


def _normalise_scalar(value: Any) -> Any:
    """Normalise individual scalar values, parsing ISO timestamps when possible."""

    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return candidate
        iso_candidate = candidate
        if candidate[-1:] in {"Z", "z"}:
            iso_candidate = f"{candidate[:-1]}+00:00"
        # ``fromisoformat`` raises ``ValueError`` if not a supported ISO timestamp.
        try:
            parsed = datetime.fromisoformat(iso_candidate)
        except ValueError:
            return candidate
        if candidate[-1:] in {"Z", "z"} and parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    return value


def normalise_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Return a normalised copy of ``metadata``.

    The function recursively converts mapping keys to snake_case, strips string
    values, and eagerly coerces ISO formatted datetimes into ``datetime``
    instances. Lists are processed element-wise to ensure nested dictionaries
    also observe the same rules. Non-mapping types are returned untouched.
    """

    def transform(obj: Any) -> Any:
        if isinstance(obj, Mapping):
            normalised: MutableMapping[str, Any] = {}
            for raw_key, value in obj.items():
                key = _normalise_key(str(raw_key))
                normalised[key] = transform(value)
            return dict(normalised)
        if isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
            return [transform(item) for item in obj]
        return _normalise_scalar(obj)

    return transform(metadata)


__all__ = ["normalise_metadata"]

