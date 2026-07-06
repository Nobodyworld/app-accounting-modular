"""Scenario plan parsing and summarisation utilities.

This module augments the snapshot orchestration layer with helpers that make
scenario plans first-class citizens.  Plans can now carry metadata, default
parameters, and descriptive tags that bubble through to diagnostics without
each caller re-implementing validation or aggregation logic.
"""

from __future__ import annotations

import json
import tomllib
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from .scenarios import SnapshotScenario

__all__ = [
    "ScenarioPlan",
    "ScenarioPlanMetadata",
    "ScenarioPlanSummary",
    "ScenarioPlanValidationError",
    "ScenarioPlanFormatError",
    "load_plan_from_bytes",
    "load_plan_from_path",
]


_SUPPORTED_DEFAULT_KEYS: Final[set[str]] = {
    "base_currency",
    "commodity_symbols",
    "jurisdictions",
    "tags",
}


class ScenarioPlanError(ValueError):
    """Base exception for scenario plan parsing issues."""


class ScenarioPlanValidationError(ScenarioPlanError):
    """Raised when plan metadata or scenarios are structurally invalid."""


class ScenarioPlanFormatError(ScenarioPlanError):
    """Raised when the raw plan bytes cannot be decoded."""


def _coerce_to_str(value: object) -> str:
    """Return a text representation, decoding byte sequences when needed."""

    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.decode()
    if isinstance(value, bytearray):
        return bytes(value).decode()
    if isinstance(value, memoryview):
        return bytes(value).decode()
    raise TypeError("Expected string-like value")


def _normalise_tags(tags: Iterable[str] | None) -> tuple[str, ...]:
    if not tags:
        return ()
    deduped: dict[str, None] = {}
    for tag in tags:
        if isinstance(tag, str | bytes):
            cleaned = _coerce_to_str(tag)
            stripped = cleaned.strip()
            if stripped:
                deduped[stripped] = None
    return tuple(deduped.keys())


def _normalise_sequence(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str | bytes):
        text_value = _coerce_to_str(value).strip()
        return (text_value,) if text_value else ()
    if isinstance(value, Iterable):
        result: list[str] = []
        for entry in value:
            if isinstance(entry, str | bytes):
                cleaned = _coerce_to_str(entry)
                stripped = cleaned.strip()
                if stripped:
                    result.append(stripped)
        return tuple(result)
    raise ScenarioPlanValidationError("Sequence defaults must be strings or iterables of strings")


def _coerce_tag_iterable(value: object) -> Iterable[str] | None:
    if value is None:
        return None
    if isinstance(value, str | bytes):
        return (_coerce_to_str(value),)
    if isinstance(value, Iterable):
        return [_coerce_to_str(item) for item in value if isinstance(item, str | bytes)]
    return None


@dataclass(slots=True)
class ScenarioPlanMetadata:
    """Descriptive metadata about a scenario plan."""

    name: str
    description: str | None = None
    tags: tuple[str, ...] = ()
    schedule: str | None = None
    parameters: Mapping[str, object] = field(default_factory=dict)

    def as_payload(self) -> dict[str, object]:
        """Return a serialisable representation of the metadata."""

        return {
            "name": self.name,
            "description": self.description,
            "tags": list(self.tags),
            "schedule": self.schedule,
            "parameters": dict(self.parameters),
        }


@dataclass(slots=True)
class ScenarioPlanSummary:
    """Lightweight aggregate describing a scenario plan."""

    scenario_count: int
    base_currencies: tuple[str, ...]
    commodity_symbols: tuple[str, ...]
    jurisdictions: tuple[str, ...]
    tags: tuple[str, ...]
    tag_counts: Mapping[str, int]
    defaults_applied: tuple[str, ...]

    def as_payload(self) -> dict[str, object]:
        return {
            "scenario_count": self.scenario_count,
            "base_currencies": list(self.base_currencies),
            "commodity_symbols": list(self.commodity_symbols),
            "jurisdictions": list(self.jurisdictions),
            "tags": list(self.tags),
            "tag_counts": dict(self.tag_counts),
            "defaults_applied": list(self.defaults_applied),
        }


@dataclass(slots=True)
class ScenarioPlan:
    """Collection of snapshot scenarios with shared metadata and defaults."""

    metadata: ScenarioPlanMetadata
    scenarios: tuple[SnapshotScenario, ...]
    defaults: Mapping[str, object]

    @classmethod
    def from_components(
        cls,
        *,
        name: str,
        scenarios: Sequence[Mapping[str, object]],
        description: str | None = None,
        tags: Iterable[str] | None = None,
        schedule: str | None = None,
        parameters: Mapping[str, object] | None = None,
        defaults: Mapping[str, object] | None = None,
    ) -> ScenarioPlan:
        """Build a plan from structured components with validation."""

        plan_name = (name or "").strip()
        if not plan_name:
            raise ScenarioPlanValidationError("Plan name must be provided")

        description_value = description.strip() if isinstance(description, str) else description
        if isinstance(description_value, str) and not description_value:
            description_value = None

        schedule_value = schedule.strip() if isinstance(schedule, str) else schedule
        if isinstance(schedule_value, str) and not schedule_value:
            schedule_value = None

        metadata = ScenarioPlanMetadata(
            name=plan_name,
            description=description_value,
            tags=_normalise_tags(tags),
            schedule=schedule_value,
            parameters=dict(parameters or {}),
        )

        defaults_mapping: dict[str, object] = {}
        default_tags: tuple[str, ...] = ()
        if defaults:
            for key, value in defaults.items():
                if key not in _SUPPORTED_DEFAULT_KEYS:
                    raise ScenarioPlanValidationError(f"Unsupported default field '{key}'")
                if key == "base_currency":
                    if not isinstance(value, str | bytes):
                        raise ScenarioPlanValidationError("Default base_currency must be a string")
                    defaults_mapping[key] = _coerce_to_str(value).strip().upper()
                elif key in {"commodity_symbols", "jurisdictions"}:
                    defaults_mapping[key] = list(_normalise_sequence(value))
                elif key == "tags":
                    default_tags = _normalise_tags(_coerce_tag_iterable(value))
                    defaults_mapping[key] = list(default_tags)

        plan_tags = metadata.tags
        scenarios_built: list[SnapshotScenario] = []
        seen_names: dict[str, None] = {}
        for index, scenario_payload in enumerate(scenarios, start=1):
            if not isinstance(scenario_payload, Mapping):
                raise ScenarioPlanValidationError(f"Scenario entry #{index} must be a mapping")

            merged: dict[str, object] = dict(defaults_mapping)
            merged.update(scenario_payload)

            scenario_tags = _normalise_tags(_coerce_tag_iterable(scenario_payload.get("tags")))
            combined_tags = _normalise_tags((*plan_tags, *default_tags, *scenario_tags))
            merged["tags"] = combined_tags

            try:
                scenario = SnapshotScenario.from_mapping(merged)
            except ValueError as exc:
                raise ScenarioPlanValidationError(str(exc)) from exc

            if scenario.name in seen_names:
                raise ScenarioPlanValidationError(f"Scenario name '{scenario.name}' must be unique")
            seen_names[scenario.name] = None
            scenarios_built.append(scenario)

        if not scenarios_built:
            raise ScenarioPlanValidationError("Plan must define at least one scenario")

        return cls(
            metadata=metadata,
            scenarios=tuple(scenarios_built),
            defaults=dict(defaults_mapping),
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> ScenarioPlan:
        if not isinstance(payload, Mapping):
            raise ScenarioPlanValidationError("Scenario plan must be a mapping")

        metadata_payload = payload.get("metadata")
        if not isinstance(metadata_payload, Mapping):
            raise ScenarioPlanValidationError("Scenario plan must include a 'metadata' object")

        defaults_payload = payload.get("defaults")
        if defaults_payload is not None and not isinstance(defaults_payload, Mapping):
            raise ScenarioPlanValidationError("Plan defaults must be a mapping")

        scenarios_payload = payload.get("scenarios")
        if not isinstance(scenarios_payload, Sequence) or isinstance(scenarios_payload, str | bytes):
            raise ScenarioPlanValidationError("Scenario plan must include a 'scenarios' array")

        return cls.from_components(
            name=str(metadata_payload.get("name", "")),
            description=(
                str(metadata_payload.get("description")) if metadata_payload.get("description") is not None else None
            ),
            tags=_normalise_tags(_coerce_tag_iterable(metadata_payload.get("tags"))),
            schedule=(str(metadata_payload.get("schedule")) if metadata_payload.get("schedule") is not None else None),
            parameters=(
                metadata_payload.get("parameters") if isinstance(metadata_payload.get("parameters"), Mapping) else {}
            ),
            defaults=defaults_payload or {},
            scenarios=[dict(entry) for entry in scenarios_payload],
        )

    def summary(self) -> ScenarioPlanSummary:
        base_currencies: dict[str, None] = {}
        commodity_symbols: dict[str, None] = {}
        jurisdictions: dict[str, None] = {}
        tag_counter: Counter[str] = Counter()

        for scenario in self.scenarios:
            base_currencies[scenario.base_currency] = None
            for symbol in scenario.commodity_symbols:
                commodity_symbols[symbol] = None
            if scenario.jurisdictions is not None:
                for jurisdiction in scenario.jurisdictions:
                    jurisdictions[jurisdiction] = None
            for tag in scenario.tags:
                tag_counter[tag] += 1

        return ScenarioPlanSummary(
            scenario_count=len(self.scenarios),
            base_currencies=tuple(base_currencies.keys()),
            commodity_symbols=tuple(commodity_symbols.keys()),
            jurisdictions=tuple(jurisdictions.keys()),
            tags=tuple(sorted(tag_counter.keys())),
            tag_counts=dict(tag_counter),
            defaults_applied=tuple(sorted(self.defaults.keys())),
        )

    def as_payload(self, include_scenarios: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "metadata": self.metadata.as_payload(),
            "defaults": dict(self.defaults),
        }
        if include_scenarios:
            payload["scenarios"] = [
                {
                    "name": scenario.name,
                    "base_currency": scenario.base_currency,
                    "commodity_symbols": list(scenario.commodity_symbols),
                    "jurisdictions": (list(scenario.jurisdictions) if scenario.jurisdictions is not None else None),
                    "tags": list(scenario.tags),
                }
                for scenario in self.scenarios
            ]
        return payload


def load_plan_from_bytes(data: bytes, *, format_hint: str | None = None) -> ScenarioPlan:
    """Decode plan bytes into a :class:`ScenarioPlan`."""

    last_error: Exception | None = None
    formats = []
    if format_hint:
        formats.append(format_hint.lower())
    formats.extend(ext for ext in (".json", ".toml") if ext not in formats)

    for suffix in formats:
        try:
            if suffix == ".json":
                payload = json.loads(data.decode("utf-8"))
            elif suffix in {".toml", ".tml"}:
                payload = tomllib.loads(data.decode("utf-8"))
            else:
                continue
        except (json.JSONDecodeError, tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
            last_error = exc
            continue

        try:
            return ScenarioPlan.from_mapping(payload)
        except ScenarioPlanValidationError as exc:
            raise exc
        except Exception as exc:  # pragma: no cover - defensive
            last_error = exc
            continue

    raise ScenarioPlanFormatError(f"Failed to decode scenario plan: {last_error}" if last_error else "Unknown format")


def load_plan_from_path(path: Path) -> ScenarioPlan:
    """Convenience wrapper to load a plan directly from disk."""

    content = path.read_bytes()
    return load_plan_from_bytes(content, format_hint=path.suffix.lower())
