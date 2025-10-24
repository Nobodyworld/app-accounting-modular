"""Application layer use cases for composing accounting data snapshots."""

from __future__ import annotations

from dataclasses import dataclass
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
    service.
    """

    base_currency: str
    commodity_symbols: Sequence[str]
    jurisdictions: Iterable[str] | None = None


class DataSnapshotService:
    """Coordinate port calls to assemble a consolidated data snapshot."""

    def __init__(
        self,
        fx_port: FXDataPort,
        commodity_port: CommodityDataPort,
        tax_port: TaxDataPort,
    ) -> None:
        self._fx_port = fx_port
        self._commodity_port = commodity_port
        self._tax_port = tax_port

    def build_snapshot(
        self,
        *,
        base_currency: str,
        commodity_symbols: Sequence[str],
        jurisdictions: Iterable[str] | None = None,
    ) -> DataSnapshot:
        """Build an immutable snapshot from the configured ports."""

        request = SnapshotRequest(
            base_currency=base_currency,
            commodity_symbols=commodity_symbols,
            jurisdictions=jurisdictions,
        )
        return self.create_snapshot(request)

    def create_snapshot(self, request: SnapshotRequest) -> DataSnapshot:
        """Build a snapshot using a pre-assembled request payload.

        The method normalises symbols and jurisdictions before touching the
        adapters, ensuring idempotent adapter calls and keeping the service easy
        to exercise in isolation.
        """

        fx_rates = tuple(
            self._fx_port.get_rates(base_currency=request.base_currency)
        )

        symbols = tuple(request.commodity_symbols)
        if symbols:
            commodity_quotes = tuple(self._commodity_port.get_quotes(symbols))
        else:
            commodity_quotes = ()

        tax_rules: tuple[TaxRule, ...]
        if request.jurisdictions is None:
            tax_rules = tuple(self._tax_port.get_rules(None))
        else:
            scope = tuple(dict.fromkeys(request.jurisdictions))
            if not scope:
                tax_rules = ()
            else:
                collected: list[TaxRule] = []
                for jurisdiction in scope:
                    collected.extend(self._tax_port.get_rules(jurisdiction))
                tax_rules = tuple(collected)

        return DataSnapshot(
            fx_rates=fx_rates,
            commodity_quotes=commodity_quotes,
            tax_rules=tax_rules,
        )
