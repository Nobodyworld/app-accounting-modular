"""Configuration utilities for the Modular Accounting application."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Mapping

from pydantic import BaseModel, Field, model_validator

__all__ = ["ProviderInfo", "Settings", "get_settings", "settings"]


class ProviderInfo(BaseModel):
    """Configuration describing an allowed provider plugin."""

    module: str
    name: str
    description: str | None = None
    capabilities: tuple[str, ...] = Field(default_factory=tuple)


DEFAULT_ALLOWED_PROVIDERS: dict[str, ProviderInfo] = {
    "fx:ecb": ProviderInfo(
        module="plugins.fx_ecb.provider",
        name="European Central Bank FX",
        description="Reference rates sourced via exchangerate.host",
        capabilities=("fx",),
    ),
    "market:yfinance": ProviderInfo(
        module="plugins.market_yfinance.provider",
        name="Yahoo Finance Market Data",
        description="Historical price data from Yahoo Finance",
        capabilities=("market",),
    ),
    "tax:oecd_stub": ProviderInfo(
        module="plugins.tax_oecd_stub.provider",
        name="OECD Tax Rules (Stub)",
        description="Demonstration tax rules sourced from an OECD stub",
        capabilities=("tax",),
    ),
}


class Settings(BaseModel):
    """Application configuration derived from environment variables."""

    database_url: str = Field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./modacct.db")
    )
    log_level: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    openex_app_id: str | None = Field(
        default_factory=lambda: os.getenv("OPENEXCHANGERATES_APP_ID")
    )
    alphavantage_key: str | None = Field(
        default_factory=lambda: os.getenv("ALPHAVANTAGE_API_KEY")
    )
    newsapi_key: str | None = Field(default_factory=lambda: os.getenv("NEWSAPI_KEY"))
    gdelt_user_agent: str | None = Field(
        default_factory=lambda: os.getenv("GDELT_USER_AGENT")
    )
    allowed_providers: dict[str, ProviderInfo] = Field(
        default_factory=lambda: {
            key: value.model_copy(deep=True)
            for key, value in DEFAULT_ALLOWED_PROVIDERS.items()
        }
    )
    jwt_secret_key: str = Field(
        default_factory=lambda: os.getenv("JWT_SECRET_KEY", "change-me")
    )
    jwt_algorithm: str = Field(
        default_factory=lambda: os.getenv("JWT_ALGORITHM", "HS256")
    )
    access_token_expire_minutes: int = Field(
        default_factory=lambda: int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    )

    @model_validator(mode="after")
    def _normalise(self) -> "Settings":
        """Sanitise string values regardless of construction path."""

        object.__setattr__(self, "database_url", (self.database_url or "").strip())
        object.__setattr__(self, "log_level", (self.log_level or "INFO").strip().upper())
        object.__setattr__(self, "openex_app_id", self._clean_optional(self.openex_app_id))
        object.__setattr__(self, "alphavantage_key", self._clean_optional(self.alphavantage_key))
        object.__setattr__(self, "newsapi_key", self._clean_optional(self.newsapi_key))
        object.__setattr__(self, "gdelt_user_agent", self._clean_optional(self.gdelt_user_agent))
        object.__setattr__(self, "jwt_secret_key", (self.jwt_secret_key or "").strip())
        object.__setattr__(
            self, "jwt_algorithm", (self.jwt_algorithm or "HS256").strip().upper()
        )
        return self

    @staticmethod
    def _clean_optional(value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @classmethod
    def load(
        cls, environ: Mapping[str, str] | None = None, prefix: str = "MODACCT_"
    ) -> "Settings":
        """Load settings from ``environ`` honoring optional ``prefix`` values."""

        env = environ or os.environ

        def lookup(field: str, *aliases: str, upper: bool = False) -> str | None:
            keys = [f"{prefix}{field.upper()}", *aliases]
            for key in keys:
                if key in env and env[key] is not None:
                    value = env[key].strip()
                    if not value:
                        return None
                    return value.upper() if upper else value
            return None

        data: dict[str, str | None] = {}
        database_url = lookup("database_url", "DATABASE_URL")
        if database_url is not None:
            data["database_url"] = database_url

        log_level = lookup("log_level", "LOG_LEVEL", upper=True)
        if log_level is not None:
            data["log_level"] = log_level

        optional_keys = {
            "openex_app_id": ("OPENEXCHANGERATES_APP_ID",),
            "alphavantage_key": ("ALPHAVANTAGE_API_KEY",),
            "newsapi_key": ("NEWSAPI_KEY",),
            "gdelt_user_agent": ("GDELT_USER_AGENT",),
        }

        for field_name, aliases in optional_keys.items():
            value = lookup(field_name, *aliases)
            if value is not None:
                data[field_name] = value

        jwt_secret = lookup("jwt_secret_key", "JWT_SECRET_KEY")
        if jwt_secret is not None:
            data["jwt_secret_key"] = jwt_secret

        jwt_algorithm = lookup("jwt_algorithm", "JWT_ALGORITHM", upper=True)
        if jwt_algorithm is not None:
            data["jwt_algorithm"] = jwt_algorithm

        expire_minutes = lookup("access_token_expire_minutes", "ACCESS_TOKEN_EXPIRE_MINUTES")
        if expire_minutes is not None:
            data["access_token_expire_minutes"] = int(expire_minutes)

        return cls(**data)


@lru_cache()
def get_settings() -> Settings:
    """Return an immutable :class:`Settings` instance."""

    return Settings()


settings = get_settings()
