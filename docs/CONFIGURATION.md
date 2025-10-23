# Configuration Guide

This guide enumerates the runtime settings for Modular Accounting, demonstrates how they are loaded, and outlines recommended hardening steps for production deployments. Settings are consumed via Pydantic's `Settings` API in `apps/api/config.py` and accept both `MODACCT_`-prefixed environment variables and a handful of compatibility aliases.

## Loading Precedence
1. Explicit overrides provided to `Settings.load(environ=...)` (used in tests).
2. Values from a dotenv file specified via `env_file` or `MODACCT_ENV_FILE`.
3. Process environment variables (prefixed with `MODACCT_` or legacy aliases).
4. Safe defaults baked into the application (ephemeral JWT secret, SQLite database, `INFO` log level).

### Sample `.env`
```dotenv
MODACCT_DATABASE_URL=postgresql+psycopg://modacct:secret@localhost:5432/modacct
MODACCT_LOG_LEVEL=INFO
MODACCT_LOG_FORMAT=JSON
MODACCT_JWT_SECRET_KEY=please-change-me-to-a-long-random-string
MODACCT_ACCESS_TOKEN_EXPIRE_MINUTES=120
MODACCT_OPENEX_APP_ID=<optional-open-exchange-rates-key>
```

Load the file explicitly when running scripts:
```bash
uvicorn apps.api.main:app --reload --env-file .env
```

## Core Settings
| Variable | Description | Default | Notes |
| --- | --- | --- | --- |
| `MODACCT_DATABASE_URL` | SQLAlchemy-compatible database URL. | `sqlite:///./modacct.db` | Accepts any SQLModel-supported backend (`postgresql+psycopg://`, `mysql+aiomysql://`, etc.). |
| `MODACCT_LOG_LEVEL` | Python logging level. | `INFO` | Valid values: `CRITICAL`, `ERROR`, `WARNING`, `INFO`, `DEBUG`. |
| `MODACCT_LOG_FORMAT` | Logging output format. | `JSON` | Choose `TEXT` locally for human-readable logs. |
| `MODACCT_ACCESS_TOKEN_EXPIRE_MINUTES` | OAuth2 access token lifetime. | `60` | Enforced to be between `1` and `43200` minutes. |
| `MODACCT_FORECAST_MAX_HORIZON` | Maximum forecast horizon. | `365` | Protects compute by capping ARIMA horizons. |

### Logging Pipeline
The application uses the shared `configure_logging` helper in `apps/observability/logging.py`. It configures:
- Request context middleware (`RequestContextMiddleware`) for HTTP correlation IDs.
- Unified formatting for Uvicorn access/error loggers and application loggers.
- CLI context managers (`logging_context` / `async_logging_context`) for background scripts.

Switch formats dynamically:
```bash
python -m cli.macli --log-format text sync-fx --base USD
```

## Security Settings
| Variable | Description | Default | Notes |
| --- | --- | --- | --- |
| `MODACCT_JWT_SECRET_KEY` | Symmetric signing secret for access tokens. | Auto-generated per process. | Must be ≥32 characters in production. Rotate periodically. |
| `MODACCT_JWT_ALGORITHM` | JOSE signing algorithm. | `HS256` | Supports HS/RS/ES variants recognised by `python-jose`. |
| `MODACCT_RATE_LIMIT_AUTH_WINDOW` | Seconds before authentication attempts are throttled. | `60` | Coordinated with `apps/api/security.py` TODO for login throttling. |

**Hardening tips**
- Inject secrets via a secret manager (Vault, AWS Secrets Manager) instead of committing `.env` files.
- Set `MODACCT_JWT_SECRET_KEY` and database credentials per environment; never rely on defaults.
- Configure HTTPS termination and ensure `Secure`/`HttpOnly` flags on session cookies if a UI proxy is added.

## Third-Party Integrations
| Variable | Description | Default | Notes |
| --- | --- | --- | --- |
| `MODACCT_OPENEX_APP_ID` | Open Exchange Rates App ID. | `None` | Enables an additional FX provider beyond the ECB stub. |
| `MODACCT_ALPHAVANTAGE_KEY` | AlphaVantage API key. | `None` | Enables stock/ETF quotes via AlphaVantage-powered plugins. |
| `MODACCT_NEWSAPI_KEY` | NewsAPI token. | `None` | Optional event ingestion for forecasting. |
| `MODACCT_GDELT_USER_AGENT` | Custom user agent for GDELT scrapes. | `None` | Recommended when polling public datasets. |

## Runtime Feature Flags
Several experimental capabilities are guarded via feature flags in `apps/api/config.py`:
- `MODACCT_ENABLE_EVENT_SIGNALS` – include event-based regressors in forecasts.
- `MODACCT_ENABLE_OTEL` – opt-in OpenTelemetry metrics/tracing emission (future milestone).

## Legacy Aliases
For compatibility with earlier deployments the following unprefixed variables are still honoured, though they will be removed in a future major release:
- `DATABASE_URL`
- `LOG_LEVEL`
- `JWT_SECRET_KEY`
- `ACCESS_TOKEN_EXPIRE_MINUTES`

Prefer the `MODACCT_` names when authoring new automation scripts to avoid migration churn.

## Troubleshooting
- **Settings validation failures** – FastAPI will surface a 500 with Pydantic validation details; run `python -m apps.api.config` locally to print the resolved settings for debugging.
- **Dotenv not loading** – ensure `python-dotenv` is installed (included in requirements) and pass `--env-file` to CLI/uvicorn when running outside FastAPI's default entrypoint.
- **Unexpected SQLite behaviour** – in-memory SQLite databases require `StaticPool`; the helper in `apps/api/db.py` enables this automatically for tests.
