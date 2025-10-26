"""Domain-level ports describing required data providers."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol, runtime_checkable

from .models import CommodityQuote, FXRate, TaxRule


@runtime_checkable
class FXDataPort(Protocol):
    """Port for retrieving FX rates from a provider."""

    def get_rates(self, base_currency: str) -> Iterable[FXRate]:
        """Fetch FX rates expressed against ``base_currency``."""


@runtime_checkable
class CommodityDataPort(Protocol):
    """Port for retrieving commodity quotes from a provider."""

    def get_quotes(self, symbols: Sequence[str]) -> Iterable[CommodityQuote]:
        """Fetch commodity quotes for the provided symbols."""


@runtime_checkable
class TaxDataPort(Protocol):
    """Port for retrieving tax rules for a jurisdiction."""

    def get_rules(self, jurisdiction: str | None = None) -> Iterable[TaxRule]:
        """Fetch tax rules optionally filtered by ``jurisdiction``.

        The application layer collapses duplicate jurisdiction requests before
        calling the port and passes ``None`` when the default/global rules are
        desired.
        """
