"""Reference adapters backed by in-memory fixtures."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Iterable, Sequence

from ..domain import CommodityQuote, FXRate, Money, TaxRule


class InMemoryFXAdapter:
    """FX adapter seeded with static rate observations.

    Parameters
    ----------
    rates:
        Mapping of quote currencies to decimal conversion factors relative to the base currency.
    """

    def __init__(self, rates: dict[str, Decimal], *, timestamp: datetime | None = None) -> None:
        self._rates = rates
        self._timestamp = timestamp or datetime.utcnow()

    def get_rates(self, base_currency: str) -> Iterable[FXRate]:
        """Return FX rates for the configured base currency.

        Parameters
        ----------
        base_currency:
            Currency code representing the base leg of the conversion.

        Yields
        ------
        FXRate
            FX rate entries for each configured quote currency.
        """

        for quote, rate in self._rates.items():
            yield FXRate(
                base_currency=base_currency,
                quote_currency=quote,
                rate=rate,
                as_of=self._timestamp,
            )


class InMemoryCommodityAdapter:
    """Commodity adapter using fixed price snapshots."""

    def __init__(self, quotes: dict[str, Decimal], currency: str = "USD") -> None:
        self._quotes = quotes
        self._currency = currency
        self._timestamp = datetime.utcnow()

    def get_quotes(self, symbols: Sequence[str]) -> Iterable[CommodityQuote]:
        """Return quotes for the requested commodity symbols.

        Parameters
        ----------
        symbols:
            Instruments to return pricing for.

        Yields
        ------
        CommodityQuote
            Quotes for each requested instrument that exists in the in-memory store.
        """

        for symbol in symbols:
            price = self._quotes.get(symbol)
            if price is None:
                continue
            yield CommodityQuote(
                symbol=symbol,
                price=Money(amount=price, currency=self._currency),
                as_of=self._timestamp,
            )


class InMemoryTaxAdapter:
    """Tax adapter returning hard-coded jurisdiction rules."""

    def __init__(self, rules: Iterable[TaxRule]) -> None:
        self._rules = tuple(rules)

    def get_rules(self, jurisdiction: str | None = None) -> Iterable[TaxRule]:
        """Return tax rules filtered by jurisdiction when requested.

        Parameters
        ----------
        jurisdiction:
            Jurisdiction code to filter the rules by.

        Yields
        ------
        TaxRule
            Matching tax rules stored in memory.
        """

        for rule in self._rules:
            if jurisdiction is None or rule.jurisdiction == jurisdiction:
                yield rule
