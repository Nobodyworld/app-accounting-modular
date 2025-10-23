# Plugin Development Guide

Modular Accounting embraces a plugin-driven model so new data sources (FX, market, tax, macro) can be added without touching the core services. This document explains the provider contracts, discovery mechanics, and packaging expectations for first- and third-party integrations.

## Anatomy of a Plugin
A plugin is a Python package under `plugins/<name>/` containing a `provider.py` module that exports a `provider()` factory. The factory returns an instance implementing the relevant protocol expected by the target service.

```
plugins/
  fx_ecb/
    __init__.py        # re-export provider + metadata
    provider.py        # implementation
```

Minimum `provider.py` skeleton:
```python
from datetime import date
from typing import Iterable

from apps.api.models.models import Rate

class MyFXProvider:
    name = "my_provider"

    def sync_daily_rates(self, base: str = "USD", date_: date | None = None) -> Iterable[Rate]:
        ...  # return Rate models (can be unsaved instances)

def provider() -> MyFXProvider:
    return MyFXProvider()
```

## Provider Contracts
| Capability | Required Methods | Used By |
| --- | --- | --- |
| FX | `sync_daily_rates(base: str, date_: date | None)` → `Iterable[Rate]` | `apps/api/services/fx_service.FXService` |
| Market Data | `sync_prices(symbol: str, start: date, end: date)` → `Iterable[Price]` | `apps/api/services/market_service.MarketService` |
| Tax | `upsert_rules()` → `Iterable[TaxRule]` | `apps/api/services/tax_service.TaxService` |

Protocols are documented inline within each service module. Providers may raise exceptions; calling services wrap failures with audit entries and logging.

## Discovery & Registration
1. Provider keys are declared in configuration (environment variables or persisted settings).
2. `apps/api/services/plugin_loader.available_providers()` imports `plugins.<name>.provider` modules and inspects exported metadata (`ProviderMetadata`).
3. Services request a provider via `load_provider(key)` which returns a handle containing metadata and a lazily-instantiated provider instance.
4. Handles cache singletons per process; stateless providers should remain side-effect free.

## Testing Plugins
- Add unit tests under `tests/plugins/test_<name>.py` to validate network calls, payload parsing, and error handling. Stub external requests using `responses` or `requests-mock`.
- Run `pytest -k plugin` locally and in CI.
- Ensure docstrings explain rate limits or required credentials.

## Packaging & Distribution
For third-party distribution consider shipping your plugin as a separate Python package that depends on `modular-accounting`. Entry-point loading (via `importlib.metadata.entry_points`) is on the roadmap; until then contributors should vendor their package under `plugins/` or add the package to `PYTHONPATH` so the loader can import it.

## Observability Expectations
- Use the shared logging helpers from `apps/observability/logging.py` when performing network requests to inherit correlation IDs.
- Surface provider metadata (e.g., API version, data source) via the returned `Rate`/`Price`/`TaxRule` instances to aid auditability.
- Honour retry/backoff semantics where upstream APIs enforce quotas; log warnings on non-retriable failures.

## Example Implementations
- [plugins/fx_ecb/provider.py](../plugins/fx_ecb/provider.py) – Fetches ECB reference rates via exchangerate.host.
- [plugins/market_yfinance/provider.py](../plugins/market_yfinance/provider.py) – Retrieves OHLC price data using yfinance.
- [plugins/tax_oecd_stub/provider.py](../plugins/tax_oecd_stub/provider.py) – Seeds placeholder OECD VAT rules for demos.

## Roadmap
Upcoming enhancements noted in `PLAN.md`:
- Entry-point driven discovery for plugins installed as external packages.
- Provider capability negotiation (FX provider that also supports commodities, etc.).
- Health-check API that validates provider connectivity and exposes status via `/core/providers`.
