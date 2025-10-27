"""Application layer use cases for composing accounting data snapshots.

This module hosts the orchestrators that bind the domain ports together
while remaining agnostic of the calling interface (API, CLI, background job,
etc.).  It also provides a small amount of input validation so consumers get
actionable feedback before network-bound adapters are invoked.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import TypeVar

from ..domain.models import CommodityQuote, FXRate, TaxRule
from ..domain.ports import CommodityDataPort, FXDataPort, TaxDataPort
from .cache import CacheStats, TTLCache
from .telemetry import SnapshotTelemetry, telemetry_provider

EMPTY_CACHE_STATS = CacheStats(size=0, hits=0, misses=0)

PortT = TypeVar("PortT", FXDataPort, CommodityDataPort, TaxDataPort)


@dataclass(slots=True)
class DataSnapshot:
    """Container aggregating data fetched from external providers."""

    fx_rates: Sequence[FXRate]
    commodity_quotes: Sequence[CommodityQuote]
    tax_rules: Sequence[TaxRule]


@dataclass(slots=True)
class SnapshotRequest:
    """Immutable request payload for building data snapshots.

    The request keeps orchestration intent detached from infrastructure so callers
    can validate or enrich the payload before handing it to the application
    service.  All collections are normalised to tuples to guarantee immutability
    when the request travels across threads or async tasks.
    """

    base_currency: str
    commodity_symbols: tuple[str, ...]
    jurisdictions: tuple[str, ...] | None = None

    @classmethod
    def from_primitives(
        cls,
        *,
        base_currency: str,
        commodity_symbols: Iterable[str] | None = None,
        jurisdictions: Iterable[str] | None = None,
    ) -> SnapshotRequest:
        """Create a normalised request from user-supplied primitives.

        Args:
            base_currency: ISO currency code that FX data should be quoted against.
            commodity_symbols: Iterable of commodity tickers the caller is
                interested in.  Duplicates and empty values are stripped and the
                remaining symbols are uppercased.
            jurisdictions: Optional iterable of jurisdictions whose tax rules
                should be fetched.  Duplicates and empty values are stripped while
                preserving order of first appearance.

        Raises:
            ValueError: If ``base_currency`` is blank after stripping whitespace.
        """

        if not isinstance(base_currency, str) or not base_currency.strip():
            raise ValueError("base_currency must be a non-empty string")

        commodity_symbols = commodity_symbols or ()
        symbol_scope = tuple(
            dict.fromkeys(
                symbol.strip().upper()
                for symbol in commodity_symbols
                if isinstance(symbol, str) and symbol.strip()
            )
        )

        if jurisdictions is None:
            jurisdiction_scope: tuple[str, ...] | None = None
        else:
            jurisdiction_scope = tuple(
                dict.fromkeys(
                    jurisdiction.strip()
                    for jurisdiction in jurisdictions
                    if isinstance(jurisdiction, str) and jurisdiction.strip()
                )
            )

        return cls(
            base_currency=base_currency.strip().upper(),
            commodity_symbols=symbol_scope,
            jurisdictions=jurisdiction_scope,
        )


class DataSnapshotService:
    """Coordinate port calls to assemble a consolidated data snapshot."""

    def __init__(
        self,
        fx_port: FXDataPort | None = None,
        commodity_port: CommodityDataPort | None = None,
        tax_port: TaxDataPort | None = None,
        *,
        fx_adapter: FXDataPort | None = None,
        commodity_adapter: CommodityDataPort | None = None,
        tax_adapter: TaxDataPort | None = None,
        enable_caching: bool = True,
        default_cache_ttl: float | None = None,
        fx_cache_ttl: float | None = None,
        commodity_cache_ttl: float | None = None,
        tax_cache_ttl: float | None = None,
        clock: Callable[[], float] | None = None,
        telemetry: SnapshotTelemetry | None = None,
        enable_telemetry: bool = True,
    ) -> None:
        """Initialise the service with adapters that satisfy the domain ports.

        Legacy ``*_adapter`` keywords are still accepted to avoid breaking older
        integrations.  When both the new ``*_port`` and legacy keyword are
        provided the port value takes precedence.

        Args:
            enable_caching: Toggle in-memory caching for adapter responses.
            default_cache_ttl: Global TTL applied to caches when a specific
                per-port TTL is not supplied. ``None`` keeps entries indefinitely.
            fx_cache_ttl: Optional TTL for FX cache entries in seconds.
            commodity_cache_ttl: Optional TTL for commodity cache entries.
            tax_cache_ttl: Optional TTL for tax cache entries.
            clock: Optional monotonic clock override used primarily for tests.
        """

        if fx_adapter is not None:
            warnings.warn(
                "fx_adapter is deprecated; pass fx_port instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        if commodity_adapter is not None:
            warnings.warn(
                "commodity_adapter is deprecated; pass commodity_port instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        if tax_adapter is not None:
            warnings.warn(
                "tax_adapter is deprecated; pass tax_port instead.",
                DeprecationWarning,
                stacklevel=2,
            )

        self._fx_port = self._choose_port(
            primary=fx_port, legacy=fx_adapter, label="fx_adapter or fx_port"
        )
        self._commodity_port = self._choose_port(
            primary=commodity_port,
            legacy=commodity_adapter,
            label="commodity_adapter or commodity_port",
        )
        self._tax_port = self._choose_port(
            primary=tax_port, legacy=tax_adapter, label="tax_adapter or tax_port"
        )

        self._enable_caching = enable_caching
        self._clock = clock
        self._telemetry = telemetry if enable_telemetry else None
        if self._telemetry is None and enable_telemetry:
            self._telemetry = telemetry_provider()

        if enable_caching:
            fx_ttl = self._validate_ttl(fx_cache_ttl, default_cache_ttl)
            commodity_ttl = self._validate_ttl(commodity_cache_ttl, default_cache_ttl)
            tax_ttl = self._validate_ttl(tax_cache_ttl, default_cache_ttl)
            fx_observer = (
                self._telemetry.cache_observer("snapshot_fx")
                if self._telemetry is not None
                else None
            )
            commodity_observer = (
                self._telemetry.cache_observer("snapshot_commodities")
                if self._telemetry is not None
                else None
            )
            tax_observer = (
                self._telemetry.cache_observer("snapshot_tax")
                if self._telemetry is not None
                else None
            )
            self._fx_cache: TTLCache[str, tuple[FXRate, ...]] | None = TTLCache(
                default_ttl=fx_ttl, clock=clock, observer=fx_observer
            )
            self._commodity_cache: TTLCache[
                tuple[str, ...], tuple[CommodityQuote, ...]
            ] | None = TTLCache(
                default_ttl=commodity_ttl,
                clock=clock,
                observer=commodity_observer,
            )
            self._tax_cache: TTLCache[
                tuple[str, ...] | None, tuple[TaxRule, ...]
            ] | None = TTLCache(
                default_ttl=tax_ttl,
                clock=clock,
                observer=tax_observer,
            )
        else:
            self._fx_cache = None
            self._commodity_cache = None
            self._tax_cache = None

    @staticmethod
    def _validate_ttl(
        specific_ttl: float | None, default_ttl: float | None
    ) -> float | None:
        ttl = specific_ttl if specific_ttl is not None else default_ttl
        if ttl is None:
            return None
        if ttl <= 0:
            raise ValueError("Cache TTL must be greater than zero when provided")
        return ttl

    @staticmethod
    def _choose_port(
        *,
        primary: PortT | None,
        legacy: PortT | None,
        label: str,
    ) -> PortT:
        """Return the selected port, preferring ``primary`` over ``legacy``."""

        port = primary if primary is not None else legacy
        if port is None:
            raise TypeError(f"DataSnapshotService requires {label}")
        return port

    def build_snapshot(
        self,
        *,
        base_currency: str,
        commodity_symbols: Sequence[str],
        jurisdictions: Iterable[str] | None = None,
    ) -> DataSnapshot:
        """Build an immutable snapshot from the configured ports."""

        request = SnapshotRequest.from_primitives(
            base_currency=base_currency,
            commodity_symbols=commodity_symbols,
            jurisdictions=jurisdictions,
        )
        return self.create_snapshot(request)

    def create_snapshot(self, request: SnapshotRequest) -> DataSnapshot:
        """Build a snapshot using a pre-assembled request payload.

        The method normalises symbols and jurisdictions before touching the
        adapters, ensuring idempotent adapter calls and keeping the service easy
        to exercise in isolation.  Adapter responses are cached in-memory per
        request scope so repeat invocations within the same process reuse data
        that is already in hand.
        """

        fx_rates = self._get_fx_rates(request.base_currency)
        timer = self._clock or perf_counter
        start = timer()
        status = "success"
        try:
            commodity_quotes = self._get_commodity_quotes(request.commodity_symbols)
            tax_rules = self._resolve_tax_rules(request)
            snapshot = DataSnapshot(
                fx_rates=fx_rates,
                commodity_quotes=commodity_quotes,
                tax_rules=tax_rules,
            )
        except Exception:
            status = "error"
            if self._telemetry is not None:
                self._telemetry.record_failure(stage="create_snapshot")
            raise
        finally:
            if self._telemetry is not None:
                duration = timer() - start
                self._telemetry.record_latency(status=status, duration=duration)

        return snapshot

    def clear_cache(self) -> None:
        """Invalidate all cached adapter responses."""

        if not self._enable_caching:
            return
        if self._fx_cache is not None:
            self._fx_cache.invalidate()
        if self._commodity_cache is not None:
            self._commodity_cache.invalidate()
        if self._tax_cache is not None:
            self._tax_cache.invalidate()

    def cache_stats(self) -> dict[str, CacheStats]:
        """Expose cache utilisation metrics for monitoring and tests."""

        if not self._enable_caching:
            return {
                "fx": EMPTY_CACHE_STATS,
                "commodities": EMPTY_CACHE_STATS,
                "tax": EMPTY_CACHE_STATS,
            }

        fx_stats = (
            self._fx_cache.stats()
            if self._fx_cache is not None
            else EMPTY_CACHE_STATS
        )
        commodity_stats = (
            self._commodity_cache.stats()
            if self._commodity_cache is not None
            else EMPTY_CACHE_STATS
        )
        tax_stats = (
            self._tax_cache.stats()
            if self._tax_cache is not None
            else EMPTY_CACHE_STATS
        )
        return {"fx": fx_stats, "commodities": commodity_stats, "tax": tax_stats}

    def _get_fx_rates(self, base_currency: str) -> tuple[FXRate, ...]:
        """Return cached FX rates for the provided ``base_currency``."""

        if not self._enable_caching or self._fx_cache is None:
            return tuple(self._fx_port.get_rates(base_currency=base_currency))

        return self._fx_cache.get_or_set(
            base_currency,
            lambda: tuple(self._fx_port.get_rates(base_currency=base_currency)),
        )

    def _get_commodity_quotes(
        self, symbols: tuple[str, ...]
    ) -> tuple[CommodityQuote, ...]:
        """Return cached commodity quotes for ``symbols`` when provided."""

        if not symbols:
            return ()

        if not self._enable_caching or self._commodity_cache is None:
            return tuple(self._commodity_port.get_quotes(symbols))

        return self._commodity_cache.get_or_set(
            symbols, lambda: tuple(self._commodity_port.get_quotes(symbols))
        )

    def _resolve_tax_rules(self, request: SnapshotRequest) -> tuple[TaxRule, ...]:
        """Collect tax rules for the request's jurisdictions."""

        jurisdictions = request.jurisdictions

        if jurisdictions is None:
            scope: tuple[str, ...] | None = None
            cache_key: tuple[str, ...] | None = None
        else:
            scope = tuple(dict.fromkeys(jurisdictions))
            if not scope:
                return ()
            cache_key = scope

        def loader() -> tuple[TaxRule, ...]:
            if scope is None:
                return tuple(self._tax_port.get_rules(None))
            collected: list[TaxRule] = []
            for jurisdiction in scope:
                collected.extend(self._tax_port.get_rules(jurisdiction))
            return tuple(collected)

        if not self._enable_caching or self._tax_cache is None:
            return loader()

        return self._tax_cache.get_or_set(cache_key, loader)
