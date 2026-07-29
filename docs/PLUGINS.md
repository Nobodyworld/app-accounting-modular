# Plugins

Plugins extend Modular Accounting with custom data providers for foreign exchange rates, commodity prices, tax rules, and market data. This guide explains how to create, test, and integrate plugins.

## Plugin Structure

Each plugin is a Python package under the `src/plugins/` directory with the following structure:

```text
src/plugins/
  your_plugin_name/
    __init__.py
    provider.py
    requirements.txt  # optional, for additional dependencies
    README.md         # optional, documentation
```

## Creating a Provider

Your plugin must expose a `provider()` factory function in `provider.py` that returns an object implementing one of the adapter contracts:

- `FXDataPort` for foreign exchange rates
- `CommodityDataPort` for commodity prices
- `TaxDataPort` for tax rules
- `MarketDataPort` for market data

### Example: FX Provider

```python
# src/plugins/fx_ecb/provider.py
from typing import Iterable

from apps.modular_accounting.domain import FXRate, Money
from plugins.provider_limits import get_bounded_json

class ECBProvider:
    def get_rates(self, base_currency: str) -> Iterable[FXRate]:
        data = get_bounded_json(
            "https://api.example.com/rates",
            provider_key="fx:example",
            operation="get-rates",
        )

        for currency, rate in data.items():
            yield FXRate(
                currency=currency,
                rate=Money(amount=rate, currency=base_currency),
                as_of=datetime.now()
            )

def provider() -> ECBProvider:
    return ECBProvider()
```

### Example: Commodity Provider

```python
# src/plugins/commodity_gold/provider.py
from apps.modular_accounting.domain import CommodityQuote, Money

class GoldPriceProvider:
    def get_quotes(self, symbols: list[str]) -> Iterable[CommodityQuote]:
        for symbol in symbols:
            if symbol == "XAU":
                # Fetch gold price
                price = self._fetch_gold_price()
                yield CommodityQuote(
                    symbol=symbol,
                    price=Money(amount=price, currency="USD"),
                    as_of=datetime.now()
                )

def provider() -> GoldPriceProvider:
    return GoldPriceProvider()
```

## Plugin Registration

Plugins are automatically discovered and loaded by the plugin loader. The loader:

1. Reads the configured provider keys from settings
2. Imports each configured plugin's `provider.py` module
3. Calls the `provider()` function to get the provider instance
4. Registers the provider with the appropriate service

## Configuration

Configure which plugins to use in your settings:

```python
# In config.py or environment variables
DEFAULT_ALLOWED_PROVIDERS = {
    "fx": ["ecb"],
    "commodity": ["gold"],
    "tax": ["oecd"]
}
```

## Best Practices

- **Outbound boundaries**: Network-backed HTTP providers must use
  `plugins.provider_limits.get_bounded_json` rather than unbounded
  `response.json()` calls.
- **Error Handling**: Return the sanitized provider-domain exceptions from
  `plugins.provider_limits`; never place response bodies, credentials, request
  parameters, or raw upstream URLs in messages or logs.
- **Caching**: Consider implementing caching to avoid excessive API calls
- **Logging**: Use structured logging for debugging and monitoring
- **Testing**: Use deterministic stubs; repository tests must not contact live
  providers or use live credentials.
- **Documentation**: Document your plugin's capabilities, limitations, and configuration

## Network-backed versus demo providers

The live outbound-provider inventory is deliberately small:

- `fx_ecb` and `fx_openexchangerates` make HTTPS GET requests through the shared
  bounded JSON reader.
- `market_yfinance` makes one high-level `yfinance.download` call.

The remaining provider packages currently generate local fixture/reference data
or act as demo adapters and perform no external I/O. Adding network I/O to one
of those packages requires the same boundary review and tests.

The shared HTTP policy permits at most 1 MiB of response bytes and 512 FX rate
records, uses separate 5-second connect and 20-second read timeouts, and permits
at most two attempts for selected transient failures. Responses are streamed,
checked against declared `Content-Length`, independently byte-counted, parsed
only after the size check, and required to contain a top-level JSON mapping.

YFinance is limited to a single application-level download call with
`threads=False`, a 20-second timeout, at most 10,000 requested days, and at most
10,000 returned price rows. Its high-level API returns an already materialized
DataFrame, so the application cannot independently stream or byte-count the
library's internal HTTP response. Any retry performed inside `yfinance` is
library-controlled; the application does not stack another retry loop.

## Reference Implementations

- `src/plugins/fx_ecb/`: ECB foreign exchange rates
- `src/plugins/market_yfinance/`: Yahoo Finance market data
- `src/plugins/tax_oecd_stub/`: OECD-style tax data reference implementation retained under its legacy package path

See [Adapter Contracts](adapters.md) for detailed interface specifications.
