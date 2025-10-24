# Adapter Contracts

Modular Accounting relies on adapter protocols to abstract tax, FX, and commodity data sources. Each adapter implements a small API so services can orchestrate data without caring about the underlying provider.

## Foreign Exchange (`FXDataAdapter`)
Implement `get_rates(base_currency: str) -> Iterable[FXRate]` to yield exchange rate observations. Rates should be denominated against the requested base currency.

## Commodity Prices (`CommodityDataAdapter`)
Implement `get_quotes(symbols: Sequence[str]) -> Iterable[CommodityQuote]` and return price snapshots for the requested instruments. Quotes include the symbol, price (as `Money`), and an `as_of` timestamp.

## Tax Rules (`TaxDataAdapter`)
Implement `get_rules(jurisdiction: str | None = None) -> Iterable[TaxRule]` to return jurisdiction-specific rules. Providers may ignore the filter or use it to reduce the response size.

## Reference Implementations
The `apps/modular_accounting/adapters/in_memory.py` module includes in-memory adapters that demonstrate the expected behaviour. Use them as templates when integrating real providers.
