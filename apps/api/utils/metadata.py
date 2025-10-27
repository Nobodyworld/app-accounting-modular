"""Utilities for normalising metadata payloads passed across API boundaries."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, MutableMapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

_SNAKE_CASE_PATTERN = re.compile(r"(?<!^)(?=[A-Z])")

JSONScalar = bool | float | int | str


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
            return parsed.replace(tzinfo=UTC)
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
        if isinstance(obj, Sequence) and not isinstance(
            obj, str | bytes | bytearray
        ):
            return [transform(item) for item in obj]
        return _normalise_scalar(obj)

    return transform(metadata)


def _coerce_json_scalar(value: Any) -> JSONScalar:
    """Coerce ``value`` into a JSON-serialisable scalar for diagnostics payloads."""

    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return str(value)
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _ensure_serialised_mapping(values: Mapping[str, Any]) -> dict[str, JSONScalar]:
    """Return ``values`` with best-effort JSON scalar coercion."""

    serialised: dict[str, JSONScalar] = {}
    for key, value in values.items():
        if value is None:
            continue
        if isinstance(value, bool | int):
            serialised[str(key)] = value
            continue
        if isinstance(value, float):
            serialised[str(key)] = (
                str(value) if math.isnan(value) or math.isinf(value) else value
            )
            continue
        serialised[str(key)] = _coerce_json_scalar(value)
    return serialised


def serialise_diagnostics(diagnostics: Mapping[str, Any]) -> dict[str, JSONScalar]:
    """Return ``diagnostics`` with keys and values coerced into JSON scalars."""

    return _ensure_serialised_mapping(diagnostics)


def merge_forecast_diagnostics(
    metadata: MutableMapping[str, Any],
    diagnostics: Mapping[str, Any] | None,
) -> MutableMapping[str, Any]:
    """Merge ``diagnostics`` into ``metadata``'s ``forecast_diagnostics`` payload."""

    if not diagnostics:
        return metadata

    existing: Mapping[str, Any] | None = None
    current = metadata.get("forecast_diagnostics")
    if isinstance(current, Mapping):
        existing = current

    merged: dict[str, JSONScalar] = {}
    if existing:
        merged.update(_ensure_serialised_mapping(existing))

    merged.update(serialise_diagnostics(diagnostics))
    metadata["forecast_diagnostics"] = merged
    return metadata


def prepare_metadata_for_response(
    metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return metadata ready for API responses.

    This function combines :func:`normalise_metadata` with diagnostics serialisation
    so callers do not need to duplicate response-shaping logic. When present, the
    ``generated_at`` field is coerced to a timezone-aware ``datetime`` instance if
    supplied as a string, and diagnostics payloads are converted into JSON-safe
    scalars.
    """

    if metadata is None:
        return {}

    normalised = normalise_metadata(metadata)

    generated_at = normalised.get("generated_at")
    if isinstance(generated_at, str):
        try:
            normalised["generated_at"] = datetime.fromisoformat(generated_at)
        except ValueError:
            # Preserve unparsable values for downstream consumers.
            pass
        else:
            generated_at = normalised["generated_at"]

    if isinstance(generated_at, datetime) and generated_at.tzinfo is None:
        normalised["generated_at"] = generated_at.replace(tzinfo=UTC)

    diagnostics = normalised.get("forecast_diagnostics")
    if isinstance(diagnostics, Mapping):
        normalised["forecast_diagnostics"] = serialise_diagnostics(diagnostics)

    return normalised


__all__ = [
    "JSONScalar",
    "normalise_metadata",
    "prepare_metadata_for_response",
    "merge_forecast_diagnostics",
    "serialise_diagnostics",
]

