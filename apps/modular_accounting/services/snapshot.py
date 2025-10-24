"""Composite services that materialise accounting snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from ..adapters import CommodityDataAdapter, FXDataAdapter, TaxDataAdapter
from ..domain import CommodityQuote, FXRate, TaxRule


@dataclass(slots=True)
class DataSnapshot:
    """Container aggregating data fetched from the configured adapters.

    Parameters
    ----------
    fx_rates:
        FX rate observations returned by the FX adapter.
    commodity_quotes:
        Commodity pricing data returned by the commodity adapter.
    tax_rules:
        Tax rules returned by the tax adapter.
    """

    fx_rates: Sequence[FXRate]
    commodity_quotes: Sequence[CommodityQuote]
    tax_rules: Sequence[TaxRule]


class DataSnapshotService:
    """Service to coordinate calls across adapters and build a snapshot view."""

    def __init__(
        self,
        fx_adapter: FXDataAdapter,
        commodity_adapter: CommodityDataAdapter,
        tax_adapter: TaxDataAdapter,
    ) -> None:
        self._fx_adapter = fx_adapter
        self._commodity_adapter = commodity_adapter
        self._tax_adapter = tax_adapter

    def build_snapshot(
        self,
        *,
        base_currency: str,
        commodity_symbols: Sequence[str],
        jurisdictions: Iterable[str] | None = None,
    ) -> DataSnapshot:
        """Build a data snapshot from all configured adapters.

        Parameters
        ----------
        base_currency:
            Currency code used when requesting FX rates.
        commodity_symbols:
            Symbols to request from the commodity adapter.
        jurisdictions:
            Optional iterable of jurisdiction codes to filter tax rules.

        Returns
        -------
        DataSnapshot
            Aggregated snapshot containing FX, commodity, and tax data.
        """

        fx_rates = tuple(self._fx_adapter.get_rates(base_currency=base_currency))
        commodity_quotes = tuple(self._commodity_adapter.get_quotes(commodity_symbols))

        jurisdiction_filter = tuple(jurisdictions or ()) or (None,)
        tax_rules: list[TaxRule] = []
        for jurisdiction in jurisdiction_filter:
            tax_rules.extend(self._tax_adapter.get_rules(jurisdiction))

        return DataSnapshot(
            fx_rates=fx_rates,
            commodity_quotes=commodity_quotes,
            tax_rules=tuple(tax_rules),
        )
