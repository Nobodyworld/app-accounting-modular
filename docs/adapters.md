# Adapter Contracts

Modular Accounting relies on adapter protocols to abstract tax, FX, and commodity data sources. Each adapter implements a small API so services can orchestrate data without caring about the underlying provider. The ports are marked as `typing.runtime_checkable`, allowing integration tests or runtime guards to verify that an adapter satisfies the expected protocol without importing the concrete implementations.

## Foreign Exchange (`FXDataPort`)
Implement `get_rates(base_currency: str) -> Iterable[FXRate]` to yield exchange rate observations. Rates should be denominated against the requested base currency.

## Commodity Prices (`CommodityDataPort`)
Implement `get_quotes(symbols: Sequence[str]) -> Iterable[CommodityQuote]` and return price snapshots for the requested instruments. Quotes include the symbol, price (as `Money`), and an `as_of` timestamp.

## Tax Rules (`TaxDataPort`)
Implement `get_rules(jurisdiction: str | None = None) -> Iterable[TaxRule]` to return jurisdiction-specific rules. Providers may ignore the filter or use it to reduce the response size. When the application layer composes a [`SnapshotRequest`](../apps/modular_accounting/application/snapshots.py), passing `None` requests the default/global rule set, while an explicit empty iterable skips the tax adapter entirely. Duplicate jurisdictions are collapsed before adapter invocation, so implementations can treat each call as unique work.

## Reference Implementations
The `apps/modular_accounting/adapters/in_memory.py` module includes in-memory adapters that demonstrate the expected behaviour. Use them as templates when integrating real providers.
