"""Orchestrators that bridge provider plugins to modular snapshot ports."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from apps.modular_accounting.application import (
    DataSnapshot,
    DataSnapshotService,
    ScenarioBatchResult,
    ScenarioSnapshotRunner,
    SnapshotDiagnostics,
    SnapshotRequest,
    SnapshotScenario,
    compute_snapshot_diagnostics,
)
from apps.modular_accounting.application.cache import CacheStats
from apps.modular_accounting.domain import CommodityQuote, FXRate, Money, TaxRule
from apps.modular_accounting.domain.ports import (
    CommodityDataPort,
    FXDataPort,
    TaxDataPort,
)

from .plugin_loader import (
    ProviderHandle,
    ProviderMetadata,
    available_providers,
    load_provider,
)

__all__ = [
    "ProviderCommodityPort",
    "ProviderFXPort",
    "ProviderTaxPort",
    "SnapshotOrchestrator",
    "SnapshotResult",
    "scenario_batch_to_payload",
]

logger = logging.getLogger(__name__)


class ProviderFXPort(FXDataPort):
    """Adapter that converts FX provider output into domain models."""

    def __init__(self, provider: Any) -> None:
        self._provider = provider

    def get_rates(self, base_currency: str) -> Iterable[FXRate]:
        rates = self._provider.sync_daily_rates(base=base_currency)
        now = datetime.now(tz=UTC)
        for record in rates:
            base = getattr(record, "base", base_currency)
            quote = getattr(record, "quote", None)
            value = getattr(record, "value", None)
            record_date = getattr(record, "date", None)
            if quote is None or value is None:
                logger.debug("Skipping FX record missing quote/value", extra={"record": record})
                continue
            as_of = datetime.combine(record_date, time.min, tzinfo=UTC) if isinstance(record_date, date) else now
            yield FXRate(
                base_currency=base,
                quote_currency=quote,
                rate=Decimal(str(value)),
                as_of=as_of,
            )


class ProviderCommodityPort(CommodityDataPort):
    """Adapter that derives commodity quotes from market providers."""

    def __init__(
        self,
        provider: Any,
        *,
        currency: str = "USD",
        lookback_days: int = 30,
        today: Callable[[], date] | None = None,
    ) -> None:
        if lookback_days <= 0:
            raise ValueError("lookback_days must be greater than zero")
        self._provider = provider
        self._currency = currency
        self._lookback_days = lookback_days
        self._today = today or date.today

    def get_quotes(self, symbols: Sequence[str]) -> Iterable[CommodityQuote]:
        if not symbols:
            return []
        end = self._today()
        start = end - timedelta(days=self._lookback_days - 1)
        for symbol in symbols:
            prices = list(self._provider.fetch_prices(symbol, start, end))
            if not prices:
                logger.debug("No market data returned", extra={"symbol": symbol})
                continue
            latest = max(
                prices,
                key=lambda price: getattr(price, "date", start),
            )
            closing = getattr(latest, "close", None)
            if closing is None:
                logger.debug("Market price missing close value", extra={"symbol": symbol})
                continue
            price_date = getattr(latest, "date", end)
            as_of = (
                datetime.combine(price_date, time.min, tzinfo=UTC)
                if isinstance(price_date, date)
                else datetime.now(tz=UTC)
            )
            yield CommodityQuote(
                symbol=symbol,
                price=Money(amount=Decimal(str(closing)), currency=self._currency),
                as_of=as_of,
            )


class ProviderTaxPort(TaxDataPort):
    """Adapter that transforms tax provider payloads into domain rules."""

    _RATE_PATTERN = re.compile(r"rate\s*=\s*(?P<rate>-?\d+(?:\.\d+)?)")

    def __init__(self, provider: Any, *, default_rate: Decimal | None = None) -> None:
        self._provider = provider
        self._default_rate = default_rate if default_rate is not None else Decimal("0")

    def get_rules(self, jurisdiction: str | None = None) -> Iterable[TaxRule]:
        rules = self._provider.upsert_rules()
        for record in rules:
            record_jurisdiction = getattr(record, "jurisdiction", None)
            if jurisdiction and record_jurisdiction != jurisdiction:
                continue
            expression = getattr(record, "expression", "") or ""
            rate = self._parse_rate(expression)
            scope = getattr(record, "scope", "tax")
            source = getattr(record, "source", None)
            description = scope if source is None else f"{scope} ({source})"
            effective_from = getattr(record, "valid_from", None) or date.today()
            effective_to = getattr(record, "valid_to", None)
            yield TaxRule(
                jurisdiction=record_jurisdiction or "unknown",
                rate=rate,
                description=description,
                effective_from=effective_from,
                effective_to=effective_to,
            )

    def _parse_rate(self, expression: str) -> Decimal:
        match = self._RATE_PATTERN.search(expression)
        if not match:
            logger.debug("Falling back to default tax rate", extra={"expression": expression})
            return self._default_rate
        return Decimal(match.group("rate"))


@dataclass(slots=True)
class SnapshotResult:
    """Composite payload returned by :class:`SnapshotOrchestrator`."""

    request: SnapshotRequest
    snapshot: DataSnapshot
    diagnostics: SnapshotDiagnostics
    providers: dict[str, str]
    cache_stats: dict[str, CacheStats]

    def as_payload(self) -> dict[str, object]:
        """Return a serialisable payload with snapshot data and metadata."""

        return {
            **snapshot_to_payload(self.snapshot, diagnostics=self.diagnostics),
            "request": {
                "base_currency": self.request.base_currency,
                "commodity_symbols": list(self.request.commodity_symbols),
                "jurisdictions": (list(self.request.jurisdictions) if self.request.jurisdictions is not None else None),
            },
            "providers": dict(self.providers),
            "cache_stats": {key: asdict(stats) for key, stats in self.cache_stats.items()},
        }


class SnapshotOrchestrator:
    """Bind provider plugins to the modular accounting snapshot service."""

    def __init__(
        self,
        *,
        fx_provider_key: str | None = None,
        commodity_provider_key: str | None = None,
        tax_provider_key: str | None = None,
        provider_loader: Callable[[str], ProviderHandle] = load_provider,
        provider_catalog: Callable[[str | None], Sequence[ProviderMetadata]] = available_providers,
        commodity_currency: str = "USD",
        commodity_lookback_days: int = 30,
    ) -> None:
        self._provider_loader = provider_loader
        self._provider_catalog = provider_catalog
        self._fx_handle = self._load_handle("fx", fx_provider_key)
        self._commodity_handle = self._load_handle("market", commodity_provider_key)
        self._tax_handle = self._load_handle("tax", tax_provider_key)
        self._commodity_port = ProviderCommodityPort(
            self._commodity_handle.instance,
            currency=commodity_currency,
            lookback_days=commodity_lookback_days,
        )
        self._service = DataSnapshotService(
            fx_port=ProviderFXPort(self._fx_handle.instance),
            commodity_port=self._commodity_port,
            tax_port=ProviderTaxPort(self._tax_handle.instance),
        )
        self._providers = {
            "fx": self._fx_handle.metadata.key,
            "commodity": self._commodity_handle.metadata.key,
            "tax": self._tax_handle.metadata.key,
        }

    def _load_handle(self, capability: str, key: str | None) -> ProviderHandle:
        resolved_key = key or self._default_key(capability)
        handle = self._provider_loader(resolved_key)
        if capability not in handle.metadata.capabilities:
            raise ValueError(f"Provider '{resolved_key}' does not advertise '{capability}' capability")
        return handle

    def _default_key(self, capability: str) -> str:
        catalog = self._provider_catalog(capability)
        if not catalog:
            raise ValueError(f"No providers configured for capability '{capability}'")
        return catalog[0].key

    def build_snapshot(
        self,
        *,
        base_currency: str,
        commodity_symbols: Sequence[str] | None = None,
        jurisdictions: Sequence[str] | None = None,
    ) -> SnapshotResult:
        request = SnapshotRequest.from_primitives(
            base_currency=base_currency,
            commodity_symbols=commodity_symbols,
            jurisdictions=jurisdictions,
        )
        snapshot = self._service.create_snapshot(request)
        diagnostics = compute_snapshot_diagnostics(snapshot, request=request)
        cache_stats = self._service.cache_stats()
        return SnapshotResult(
            request=request,
            snapshot=snapshot,
            diagnostics=diagnostics,
            providers=dict(self._providers),
            cache_stats=cache_stats,
        )

    def run_scenarios(
        self,
        scenarios: Sequence[SnapshotScenario],
        *,
        reset_cache_between_runs: bool = False,
    ) -> ScenarioBatchResult:
        """Execute a batch of snapshot scenarios using the configured providers."""

        if not scenarios:
            raise ValueError("At least one scenario must be provided")

        runner = ScenarioSnapshotRunner(self._service, reset_cache_between_runs=reset_cache_between_runs)
        return runner.run(scenarios, providers=dict(self._providers))


def snapshot_to_payload(snapshot: DataSnapshot, diagnostics: SnapshotDiagnostics | None = None) -> dict[str, object]:
    """Return a dictionary representation of :class:`DataSnapshot`."""

    payload = {
        "fx_rates": [
            {
                "base_currency": rate.base_currency,
                "quote_currency": rate.quote_currency,
                "rate": rate.rate,
                "as_of": rate.as_of,
            }
            for rate in snapshot.fx_rates
        ],
        "commodity_quotes": [
            {
                "symbol": quote.symbol,
                "price": asdict(quote.price),
                "as_of": quote.as_of,
            }
            for quote in snapshot.commodity_quotes
        ],
        "tax_rules": [
            {
                "jurisdiction": rule.jurisdiction,
                "rate": rule.rate,
                "description": rule.description,
                "effective_from": rule.effective_from,
                "effective_to": rule.effective_to,
            }
            for rule in snapshot.tax_rules
        ],
    }
    if diagnostics is not None:
        payload["diagnostics"] = asdict(diagnostics)
    return payload


def scenario_batch_to_payload(batch: ScenarioBatchResult) -> dict[str, object]:
    """Convert a :class:`ScenarioBatchResult` into an API-friendly payload."""

    results_payload: list[dict[str, object]] = []
    for result in batch.results:
        scenario_payload = snapshot_to_payload(result.snapshot, diagnostics=result.diagnostics)
        scenario_payload.update(
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
                "providers": dict(result.providers) if result.providers else None,
                "cache_stats": {name: asdict(stats) for name, stats in result.cache_stats.items()},
            }
        )
        results_payload.append(scenario_payload)

    summary = batch.summary
    summary_payload = {
        "scenario_count": summary.scenario_count,
        "base_currencies": list(summary.base_currencies),
        "commodity_symbols": list(summary.commodity_symbols),
        "jurisdictions": list(summary.jurisdictions),
        "missing_sections": {name: list(sections) for name, sections in summary.missing_sections.items()},
        "total_fx_rates": summary.total_fx_rates,
        "total_commodity_quotes": summary.total_commodity_quotes,
        "total_tax_rules": summary.total_tax_rules,
        "max_fx_age_seconds": summary.max_fx_age_seconds,
        "max_commodity_age_seconds": summary.max_commodity_age_seconds,
        "max_active_tax_rules": summary.max_active_tax_rules,
    }

    return {"results": results_payload, "summary": summary_payload}
