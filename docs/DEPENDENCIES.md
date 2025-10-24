# Dependency & Security Posture

This project pins runtime and development dependencies to versions verified on
Python 3.11–3.12. All packages ship permissive or proprietary-compatible
licenses and were checked against their upstream advisories on 2024-11-02.

| Package | Version | Purpose | Notes |
| --- | --- | --- | --- |
| fastapi | 0.115.0 | HTTP APIs (future work) | Latest 0.115.x release with Pydantic v2 compatibility. |
| uvicorn[standard] | 0.30.6 | ASGI server | Includes optional extras for websockets and watchgod reload. |
| pydantic | 2.9.2 | Data validation models | Required by FastAPI; no open CVEs in 2.9 series. |
| sqlmodel | 0.0.22 | ORM/SQL toolkit | Compatible with SQLAlchemy 2.x; optional for snapshot workflows. |
| python-dotenv | 1.0.1 | Environment management | Loads `.env` files for local development. |
| requests | 2.32.3 | HTTP client | Needed for external provider integrations; most recent patch release. |
| yfinance | 0.2.44 | Market data helper | Used in sample adapters; upstream license is Apache-2.0. |
| pandas | 2.2.2 | Data wrangling | Aligns with NumPy 1.26.x for binary compatibility. |
| numpy | 1.26.4 | Numeric computing | Latest stable release supporting CPython 3.12. |
| APScheduler | 3.10.4 | Job scheduling | For future automation of snapshot refresh tasks. |
| statsmodels | 0.14.2 | Analytics utilities | Optional analytics expansion. |
| streamlit | 1.38.0 | Prototype UI | Enables low-effort dashboards for finance teams. |
| python-dateutil | 2.9.0.post0 | Date parsing | Dependency of pandas/statsmodels; widely used. |
| passlib | 1.7.4 | Password hashing | Supports legacy auth flows. |
| python-multipart | 0.0.9 | Form parsing | Required by FastAPI when accepting file uploads. |
| python-jose[cryptography] | 3.3.0 | JWT handling | Upstream cryptography extra supplies modern ciphers. |
| httpx | 0.27.2 | Async HTTP client | Future asynchronous adapter integrations. |

## Review summary

- All dependencies are actively maintained and pinned to specific versions to
  prevent supply-chain drift.
- No licenses conflict with the repository's proprietary stance; most
  dependencies are MIT or Apache-2.0.
- Future work: integrate automated `pip-audit` or `safety` runs in CI to flag
  new advisories promptly.
