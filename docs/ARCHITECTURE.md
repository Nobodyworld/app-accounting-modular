# Architecture

```
modular-accounting/
  apps/
    api/                # FastAPI service
    web/                # Streamlit UI
  cli/                  # CLI commands
  plugins/              # First-party plugins
  docs/                 # Docs
```

## Data Model (core)

- `Account`: type (Asset/Liability/Equity/Revenue/Expense)
- `Transaction`: source/vendor/payee, date, meta
- `JournalEntry`: double-entry postings (debit/credit, account_id, amount, currency)
- `Instrument`: equity/etf/commodity/currency with ticker/symbol
- `Price`: instrument_id, date, close, provider
- `Rate`: fx rate base/quote, date, value
- `TaxRule`: jurisdiction, scope, expression
- `Event`: news/macro marker

## Plugin Contracts

```
class BaseFXProvider(Protocol):
    name: str
    def sync_daily_rates(self, base: str, date: date | None = None) -> list[Rate]: ...

class BaseMarketProvider(Protocol):
    name: str
    def fetch_prices(self, symbol: str, start: date, end: date) -> list[Price]: ...

class BaseTaxProvider(Protocol):
    name: str
    def upsert_rules(self) -> list[TaxRule]: ...
```

Providers register with `apps.api.services.plugin_loader` and are addressable via `/providers` endpoints.

## Forecasting

`ForecastService` composes:
- Time-series model (ARIMA baseline)
- Optional exogenous features: event intensities, FX volatility, commodities, macro

## Storage

- Default: SQLite (file `modacct.db`)
- Swap by setting `DATABASE_URL` to Postgres/MySQL etc.

## Jobs

- APScheduler in-process for simple cron-like jobs (upgrade to Celery/Redis for scale)
- Scheduler lifecycle is centralised in `apps.api.scheduler` with a process-wide lock to prevent duplicate job registration under reloads.

## Security & Audit

- JWT-based auth with PBKDF2 password hashing.
- `/auth/token` endpoint enforces rate-limits and records each attempt via `AuditLogger` (`AuditAction.ACCESS`).
- Audit events are appended to `AuditLog` with the acting user/request metadata for traceability.
