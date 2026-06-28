"""Batch orchestration utilities for snapshot scenario analysis.

This module builds on top of :mod:`apps.modular_accounting.application.snapshots`
to execute groups of :class:`~apps.modular_accounting.application.snapshots.SnapshotRequest`
objects and derive portfolio-style diagnostics.  It keeps the orchestration
logic free of I/O concerns so both the API and CLI layers can reuse the
implementation without bespoke glue code.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass

from apps.observability.metrics import scenario_telemetry
from apps.observability.tracing import traced

from .cache import CacheStats
from .diagnostics import SnapshotDiagnostics, compute_snapshot_diagnostics
from .snapshots import DataSnapshot, DataSnapshotService, SnapshotRequest

__all__ = [
    "SnapshotScenario",
    "ScenarioResult",
    "ScenarioSummary",
    "ScenarioBatchResult",
    "ScenarioSnapshotRunner",
]


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SnapshotScenario:
    """Immutable definition describing a snapshot execution scenario."""

    name: str
    request: SnapshotRequest
    tags: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> SnapshotScenario:
        """Construct a scenario from a mapping, typically loaded from JSON."""

        def _scope_values(value: object) -> Iterable[str] | None:
            if value is None:
                return None
            if isinstance(value, str | bytes):
                token = value.decode() if isinstance(value, bytes) else value
                normalized = token.strip()
                return (normalized,) if normalized else ()
            if isinstance(value, Iterable):
                scoped: list[str] = []
                for item in value:
                    if isinstance(item, str | bytes):
                        token = item.decode() if isinstance(item, bytes) else item
                        normalized = token.strip()
                        if normalized:
                            scoped.append(normalized)
                return tuple(scoped)
            return ()

        raw_name = str(payload.get("name", "") or "").strip()
        if not raw_name:
            raise ValueError("Scenario name must be provided")

        tags_value = payload.get("tags", ())
        if isinstance(tags_value, str):
            tag_iterable: Iterable[str] = (tags_value,)
        elif isinstance(tags_value, Iterable):
            tag_iterable = (str(tag) for tag in tags_value if isinstance(tag, str | bytes))
        else:
            tag_iterable = ()

        tags = tuple(dict.fromkeys(tag.strip() for tag in tag_iterable if tag and tag.strip()))

        commodity_symbols = _scope_values(payload.get("commodity_symbols"))
        jurisdictions = _scope_values(payload.get("jurisdictions"))

        request = SnapshotRequest.from_primitives(
            base_currency=str(payload.get("base_currency", "")),
            commodity_symbols=commodity_symbols,
            jurisdictions=jurisdictions,
        )

        return cls(name=raw_name, request=request, tags=tags)

    @property
    def base_currency(self) -> str:
        """Return the scenario's base currency."""

        return self.request.base_currency

    @property
    def commodity_symbols(self) -> tuple[str, ...]:
        """Return commodity symbols referenced by the scenario."""

        return self.request.commodity_symbols

    @property
    def jurisdictions(self) -> tuple[str, ...] | None:
        """Return jurisdictions covered by the scenario."""

        return self.request.jurisdictions


@dataclass(slots=True)
class ScenarioResult:
    """Concrete snapshot outcome for a :class:`SnapshotScenario`."""

    scenario: SnapshotScenario
    snapshot: DataSnapshot
    diagnostics: SnapshotDiagnostics
    cache_stats: dict[str, CacheStats]
    providers: dict[str, str] | None = None


@dataclass(slots=True)
class ScenarioSummary:
    """Aggregated metrics describing a batch of scenario results."""

    scenario_count: int
    base_currencies: tuple[str, ...]
    commodity_symbols: tuple[str, ...]
    jurisdictions: tuple[str, ...]
    missing_sections: dict[str, tuple[str, ...]]
    total_fx_rates: int
    total_commodity_quotes: int
    total_tax_rules: int
    max_fx_age_seconds: float | None
    max_commodity_age_seconds: float | None
    max_active_tax_rules: int

    @classmethod
    def from_results(cls, results: Sequence[ScenarioResult]) -> ScenarioSummary:
        scenario_count = len(results)
        currencies: dict[str, None] = {}
        symbols: dict[str, None] = {}
        jurisdictions: dict[str, None] = {}
        missing: dict[str, tuple[str, ...]] = {}
        total_fx = 0
        total_commodities = 0
        total_tax = 0
        max_fx_age: float | None = None
        max_commodity_age: float | None = None
        max_active_tax = 0

        for result in results:
            diagnostics = result.diagnostics
            base_currency = diagnostics.base_currency or result.scenario.base_currency
            currencies[base_currency] = None
            for symbol in result.scenario.commodity_symbols:
                symbols[symbol] = None
            for symbol in diagnostics.commodity_symbols:
                symbols[symbol] = None
            if result.scenario.jurisdictions is not None:
                for jurisdiction in result.scenario.jurisdictions:
                    jurisdictions[jurisdiction] = None
            else:
                for jurisdiction in diagnostics.tax_jurisdictions:
                    jurisdictions[jurisdiction] = None

            total_fx += diagnostics.fx_rate_count
            total_commodities += diagnostics.commodity_quote_count
            total_tax += diagnostics.tax_rule_count
            if diagnostics.fx_max_age_seconds is not None:
                max_fx_age = (
                    diagnostics.fx_max_age_seconds
                    if max_fx_age is None
                    else max(max_fx_age, diagnostics.fx_max_age_seconds)
                )
            if diagnostics.commodity_max_age_seconds is not None:
                max_commodity_age = (
                    diagnostics.commodity_max_age_seconds
                    if max_commodity_age is None
                    else max(max_commodity_age, diagnostics.commodity_max_age_seconds)
                )
            max_active_tax = max(max_active_tax, diagnostics.active_tax_rule_count)
            if diagnostics.missing_sections:
                missing[result.scenario.name] = diagnostics.missing_sections

        return cls(
            scenario_count=scenario_count,
            base_currencies=tuple(currencies.keys()),
            commodity_symbols=tuple(symbols.keys()),
            jurisdictions=tuple(jurisdictions.keys()),
            missing_sections=missing,
            total_fx_rates=total_fx,
            total_commodity_quotes=total_commodities,
            total_tax_rules=total_tax,
            max_fx_age_seconds=max_fx_age,
            max_commodity_age_seconds=max_commodity_age,
            max_active_tax_rules=max_active_tax,
        )


@dataclass(slots=True)
class ScenarioBatchResult:
    """Batch execution response for a sequence of scenarios."""

    results: tuple[ScenarioResult, ...]
    summary: ScenarioSummary

    def as_payload(self) -> dict[str, object]:
        """Return a JSON-serialisable representation of the batch result."""

        payload_results = []
        for result in self.results:
            payload_results.append(
                {
                    "name": result.scenario.name,
                    "tags": list(result.scenario.tags),
                    "request": {
                        "base_currency": result.scenario.base_currency,
                        "commodity_symbols": list(result.scenario.commodity_symbols),
                        "jurisdictions": (
                            list(result.scenario.jurisdictions) if result.scenario.jurisdictions is not None else None
                        ),
                    },
                    "diagnostics": asdict(result.diagnostics),
                    "cache_stats": {name: asdict(stats) for name, stats in result.cache_stats.items()},
                    "providers": dict(result.providers) if result.providers else None,
                    "snapshot": {
                        "fx_rates": [asdict(rate) for rate in result.snapshot.fx_rates],
                        "commodity_quotes": [
                            {
                                **asdict(quote),
                                "price": asdict(quote.price),
                            }
                            for quote in result.snapshot.commodity_quotes
                        ],
                        "tax_rules": [asdict(rule) for rule in result.snapshot.tax_rules],
                    },
                }
            )

        summary_payload = {
            "scenario_count": self.summary.scenario_count,
            "base_currencies": list(self.summary.base_currencies),
            "commodity_symbols": list(self.summary.commodity_symbols),
            "jurisdictions": list(self.summary.jurisdictions),
            "missing_sections": {name: list(sections) for name, sections in self.summary.missing_sections.items()},
            "total_fx_rates": self.summary.total_fx_rates,
            "total_commodity_quotes": self.summary.total_commodity_quotes,
            "total_tax_rules": self.summary.total_tax_rules,
            "max_fx_age_seconds": self.summary.max_fx_age_seconds,
            "max_commodity_age_seconds": self.summary.max_commodity_age_seconds,
            "max_active_tax_rules": self.summary.max_active_tax_rules,
        }

        return {"results": payload_results, "summary": summary_payload}


class ScenarioSnapshotRunner:
    """Execute snapshot scenarios using a shared :class:`DataSnapshotService`."""

    def __init__(
        self,
        service: DataSnapshotService,
        *,
        reset_cache_between_runs: bool = False,
    ) -> None:
        self._service = service
        self._reset_cache = reset_cache_between_runs

    def run(
        self,
        scenarios: Sequence[SnapshotScenario],
        *,
        providers: dict[str, str] | None = None,
    ) -> ScenarioBatchResult:
        """Execute ``scenarios`` sequentially and gather diagnostics."""

        results: list[ScenarioResult] = []
        for scenario in scenarios:
            tag_tuple = tuple(scenario.tags)
            trace_tags = ",".join(tag_tuple) if tag_tuple else ""
            with traced(
                "scenarios.run",
                scenario=scenario.name,
                tags=trace_tags,
            ):
                with scenario_telemetry.track(scenario=scenario.name, tags=tag_tuple):
                    if self._reset_cache:
                        self._service.clear_cache()
                    snapshot = self._service.create_snapshot(scenario.request)
                    diagnostics = compute_snapshot_diagnostics(snapshot, request=scenario.request)
                    cache_stats = self._service.cache_stats()
                logger.info(
                    "Scenario executed",
                    extra={
                        "scenario": scenario.name,
                        "tags": tag_tuple,
                        "fx_rates": diagnostics.fx_rate_count,
                        "commodity_quotes": diagnostics.commodity_quote_count,
                        "tax_rules": diagnostics.tax_rule_count,
                    },
                )
            results.append(
                ScenarioResult(
                    scenario=scenario,
                    snapshot=snapshot,
                    diagnostics=diagnostics,
                    cache_stats=cache_stats,
                    providers=providers,
                )
            )

        summary = ScenarioSummary.from_results(results)
        logger.info(
            "Scenario batch completed",
            extra={
                "scenario_count": summary.scenario_count,
                "base_currencies": summary.base_currencies,
                "missing_sections": summary.missing_sections,
            },
        )
        return ScenarioBatchResult(results=tuple(results), summary=summary)
