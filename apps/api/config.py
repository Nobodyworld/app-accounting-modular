"""Configuration utilities for the Modular Accounting application."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel, Field

__all__ = ["Settings", "get_settings", "settings"]


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


@lru_cache()
def get_settings() -> Settings:
    """Return an immutable :class:`Settings` instance."""

    return Settings()


settings = get_settings()
