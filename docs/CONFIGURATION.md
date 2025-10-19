# Configuration Guide

This document outlines the runtime configuration surface for the Modular Accounting platform. Settings are consumed via environment variables using the `MODACCT_` prefix. A starter `.env.example` file lives in the repository root; copy it to `.env` (or another path) and provide deployment-specific secrets before launching any services.

## Loading precedence

1. Values supplied via function arguments/tests (`Settings.load(environ=...)`).
2. Keys loaded from an explicit dotenv file passed to `Settings.load(env_file=...)` or referenced by the `MODACCT_ENV_FILE` environment variable.
3. Process environment variables (prefixed by `MODACCT_` or legacy aliases as noted below).
4. Secure defaults baked into the application (ephemeral JWT secret, SQLite development database, `INFO` log level).

## Core settings

| Variable | Description | Default | Notes |
| --- | --- | --- | --- |
| `MODACCT_DATABASE_URL` | SQLAlchemy-compatible database URL | `sqlite:///./modacct.db` | Must include a scheme (e.g. `postgresql://`). |
| `MODACCT_LOG_LEVEL` | Python logging level | `INFO` | Valid values: `CRITICAL`, `ERROR`, `WARNING`, `INFO`, `DEBUG`, etc. |
| `MODACCT_ACCESS_TOKEN_EXPIRE_MINUTES` | OAuth2 access token lifetime in minutes | `60` | Must be between `1` and `43200` (30 days). |

## Security

| Variable | Description | Default | Notes |
| --- | --- | --- | --- |
| `MODACCT_JWT_SECRET_KEY` | Symmetric signing secret for JWT tokens | Auto-generated at startup | Provide a stable, ≥32 character secret for persistent deployments. |
| `MODACCT_JWT_ALGORITHM` | JOSE signing algorithm | `HS256` | Supported algorithms: `HS256`, `HS384`, `HS512`, `RS256`, `RS384`, `RS512`, `ES256`, `ES384`, `ES512`. |

## Third-party integrations

| Variable | Description | Default | Notes |
| --- | --- | --- | --- |
| `MODACCT_OPENEX_APP_ID` | Open Exchange Rates App ID | `None` | Optional; enables Open Exchange Rates provider. |
| `MODACCT_ALPHAVANTAGE_KEY` | AlphaVantage API key | `None` | Optional market data provider. |
| `MODACCT_NEWSAPI_KEY` | NewsAPI authentication token | `None` | Optional news ingestion. |
| `MODACCT_GDELT_USER_AGENT` | Custom user agent for GDELT requests | `None` | Optional; recommended when enabling GDELT fetcher. |

## Dotenv usage

Callers can specify a dotenv file path via the `MODACCT_ENV_FILE` environment variable or the `env_file` argument when calling `Settings.load`. Dotenv files are parsed using [`python-dotenv`](https://saurabh-kumar.com/python-dotenv/) and merged into the process environment without overriding already-defined keys by default. Pass `override_env_file=True` if the dotenv should take precedence.

## Legacy aliases

For backward compatibility, several unprefixed environment variables remain supported: `DATABASE_URL`, `LOG_LEVEL`, `JWT_SECRET_KEY`, and `ACCESS_TOKEN_EXPIRE_MINUTES`. Prefer the prefixed equivalents for new deployments.
