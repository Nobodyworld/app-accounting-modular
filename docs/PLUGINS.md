# Plugins

Plugins extend Modular Accounting with custom data providers for foreign exchange rates, commodity prices, tax rules, and market data. This guide explains how to create, test, and integrate plugins.

## Plugin Structure

Each plugin is a Python package under the `plugins/` directory with the following structure:

```text
plugins/
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
# plugins/fx_ecb/provider.py
import requests
from typing import Iterable
from apps.modular_accounting.domain import FXRate, Money

class ECBProvider:
    def get_rates(self, base_currency: str) -> Iterable[FXRate]:
        # Fetch rates from ECB API
        response = requests.get("https://api.example.com/rates")
        data = response.json()

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
# plugins/commodity_gold/provider.py
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

1. Scans the `plugins/` directory
2. Imports each plugin's `provider.py` module
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

- **Error Handling**: Implement robust error handling for network requests and data parsing
- **Caching**: Consider implementing caching to avoid excessive API calls
- **Logging**: Use structured logging for debugging and monitoring
- **Testing**: Include unit tests for your plugin
- **Documentation**: Document your plugin's capabilities, limitations, and configuration

## Reference Implementations

- `plugins/fx_ecb/`: ECB foreign exchange rates
- `plugins/market_yfinance/`: Yahoo Finance market data
- `plugins/tax_oecd_stub/`: OECD tax rules stub

See [Adapter Contracts](adapters.md) for detailed interface specifications.
