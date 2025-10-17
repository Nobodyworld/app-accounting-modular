"""Centralised configuration management for the API layer."""

from __future__ import annotations

import os
from typing import Iterable

from pydantic import BaseModel, Field, field_validator

_ENV_ALIASES: dict[str, tuple[str, ...]] = {
    "database_url": ("MODACCT_DATABASE_URL", "DATABASE_URL"),
    "log_level": ("MODACCT_LOG_LEVEL", "LOG_LEVEL"),
    "openex_app_id": ("MODACCT_OPENEX_APP_ID", "OPENEXCHANGERATES_APP_ID"),
    "alphavantage_key": ("MODACCT_ALPHAVANTAGE_KEY", "ALPHAVANTAGE_API_KEY"),
    "newsapi_key": ("MODACCT_NEWSAPI_KEY", "NEWSAPI_KEY"),
    "gdelt_user_agent": ("MODACCT_GDELT_USER_AGENT", "GDELT_USER_AGENT"),
}


def _first_env(aliases: Iterable[str]) -> str | None:
    for key in aliases:
        value = os.getenv(key)
        if value is not None:
            return value
    return None


class Settings(BaseModel):
    """Application configuration sourced from environment variables."""

    model_config = {"extra": "ignore"}

    database_url: str = Field(default="sqlite:///./modacct.db")
    log_level: str = Field(default="INFO")
    openex_app_id: str | None = Field(default=None)
    alphavantage_key: str | None = Field(default=None)
    newsapi_key: str | None = Field(default=None)
    gdelt_user_agent: str | None = Field(default=None)

    @classmethod
    def load(cls) -> "Settings":
        data: dict[str, str | None] = {}
        for field, aliases in _ENV_ALIASES.items():
            value = _first_env(aliases)
            if value is not None:
                data[field] = value
        return cls(**data)

    @field_validator("database_url")
    @classmethod
    def _strip_database_url(cls, value: str) -> str:
        return value.strip()

    @field_validator("log_level")
    @classmethod
    def _normalise_log_level(cls, value: str) -> str:
        value = value.strip()
        return value.upper() or "INFO"

    @field_validator(
        "openex_app_id",
        "alphavantage_key",
        "newsapi_key",
        "gdelt_user_agent",
    )
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


settings = Settings.load()
