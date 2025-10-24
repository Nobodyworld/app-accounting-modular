"""Application layer use cases for composing accounting data snapshots.

This module hosts the orchestrators that bind the domain ports together
while remaining agnostic of the calling interface (API, CLI, background job,
etc.).  It also provides a small amount of input validation so consumers get
actionable feedback before network-bound adapters are invoked.
"""

from __future__ import annotations

from dataclasses import dataclass
import warnings
from typing import Iterable, Sequence

from ..domain.models import CommodityQuote, FXRate, TaxRule
from ..domain.ports import CommodityDataPort, FXDataPort, TaxDataPort


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
    ) -> "SnapshotRequest":
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
    ) -> None:
        """Initialise the service with adapters that satisfy the domain ports.

        Legacy ``*_adapter`` keywords are still accepted to avoid breaking older
        integrations.  When both the new ``*_port`` and legacy keyword are
        provided the port value takes precedence.
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

        self._fx_cache: dict[str, tuple[FXRate, ...]] = {}
        self._commodity_cache: dict[tuple[str, ...], tuple[CommodityQuote, ...]] = {}
        self._tax_cache: dict[tuple[str, ...] | None, tuple[TaxRule, ...]] = {}

    @staticmethod
    def _choose_port(
        *,
        primary: FXDataPort | CommodityDataPort | TaxDataPort | None,
        legacy: FXDataPort | CommodityDataPort | TaxDataPort | None,
        label: str,
    ) -> FXDataPort | CommodityDataPort | TaxDataPort:
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
        commodity_quotes = self._get_commodity_quotes(request.commodity_symbols)
        tax_rules = self._resolve_tax_rules(request)

        return DataSnapshot(
            fx_rates=fx_rates,
            commodity_quotes=commodity_quotes,
            tax_rules=tax_rules,
        )

    def _get_fx_rates(self, base_currency: str) -> tuple[FXRate, ...]:
        """Return cached FX rates for the provided ``base_currency``."""

        if base_currency not in self._fx_cache:
            self._fx_cache[base_currency] = tuple(
                self._fx_port.get_rates(base_currency=base_currency)
            )
        return self._fx_cache[base_currency]

    def _get_commodity_quotes(
        self, symbols: tuple[str, ...]
    ) -> tuple[CommodityQuote, ...]:
        """Return cached commodity quotes for ``symbols`` when provided."""

        if not symbols:
            return ()

        if symbols not in self._commodity_cache:
            self._commodity_cache[symbols] = tuple(
                self._commodity_port.get_quotes(symbols)
            )
        return self._commodity_cache[symbols]

    def _resolve_tax_rules(self, request: SnapshotRequest) -> tuple[TaxRule, ...]:
        """Collect tax rules for the request's jurisdictions."""

        jurisdictions = request.jurisdictions

        if jurisdictions is None:
            scope: tuple[str, ...] | None = None
            cache_key = None
        else:
            scope = tuple(dict.fromkeys(jurisdictions))
            if not scope:
                return ()
            cache_key = scope

        if cache_key not in self._tax_cache:
            if scope is None:
                fetched = tuple(self._tax_port.get_rules(None))
            else:
                collected: list[TaxRule] = []
                for jurisdiction in scope:
                    collected.extend(self._tax_port.get_rules(jurisdiction))
                fetched = tuple(collected)
            self._tax_cache[cache_key] = fetched

        return self._tax_cache[cache_key]
