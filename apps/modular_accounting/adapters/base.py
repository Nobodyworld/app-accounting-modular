"""Adapter protocols describing external data integrations."""

from __future__ import annotations

from typing import Iterable, Protocol, Sequence

from ..domain import CommodityQuote, FXRate, TaxRule


class FXDataAdapter(Protocol):
    """Protocol for retrieving FX rates from a provider.

    Methods
    -------
    get_rates(base_currency)
        Return an iterable of :class:`FXRate` values against ``base_currency``.
    """

    def get_rates(self, base_currency: str) -> Iterable[FXRate]:
        """Fetch FX rates for the given base currency.

        Parameters
        ----------
        base_currency:
            ISO 4217 currency to express the rates against.

        Returns
        -------
        Iterable[FXRate]
            Sequence of FX rate observations.
        """

    
class CommodityDataAdapter(Protocol):
    """Protocol for retrieving commodity quotes from a provider.

    Methods
    -------
    get_quotes(symbols)
        Return quotes for the requested symbols.
    """

    def get_quotes(self, symbols: Sequence[str]) -> Iterable[CommodityQuote]:
        """Fetch commodity quotes for the provided symbols.

        Parameters
        ----------
        symbols:
            Collection of commodity identifiers to load.

        Returns
        -------
        Iterable[CommodityQuote]
            Quotes available for the requested instruments.
        """


class TaxDataAdapter(Protocol):
    """Protocol for retrieving tax rules for a jurisdiction.

    Methods
    -------
    get_rules(jurisdiction)
        Return available tax rules, optionally filtered by jurisdiction.
    """

    def get_rules(self, jurisdiction: str | None = None) -> Iterable[TaxRule]:
        """Fetch tax rules from the provider.

        Parameters
        ----------
        jurisdiction:
            Optional jurisdiction filter for the returned rules.

        Returns
        -------
        Iterable[TaxRule]
            Rules produced by the provider.
        """
