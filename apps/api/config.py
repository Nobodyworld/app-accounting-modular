"""Configuration utilities for the Modular Accounting application."""

from __future__ import annotations

import logging
import os
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, cast

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

__all__ = ["ProviderInfo", "Settings", "get_settings", "settings"]

logger = logging.getLogger(__name__)


VALID_LOG_LEVELS = frozenset(
    name
    for name, level in logging.getLevelNamesMapping().items()
    if isinstance(level, int)
)

DEFAULT_LOG_LEVEL = "INFO"

ALLOWED_JWT_ALGORITHMS = frozenset(
    {
        "HS256",
        "HS384",
        "HS512",
        "RS256",
        "RS384",
        "RS512",
        "ES256",
        "ES384",
        "ES512",
    }
)

MAX_ACCESS_TOKEN_MINUTES = 60 * 24 * 30  # 30 days


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

# TODO - Load provider catalog from persistence so admin edits survive restarts.

_SECRET_PROVENANCE: dict[str, bool] = {}


def _resolve_jwt_secret(
    environ: Mapping[str, str] | None = None, prefix: str = "MODACCT_"
) -> tuple[str, bool]:
    """Return a JWT secret and whether it was auto-generated."""

    env = environ or os.environ
    for key in (f"{prefix}JWT_SECRET_KEY", "JWT_SECRET_KEY"):
        value = env.get(key)
        if value is None:
            continue
        trimmed = value.strip()
        if trimmed:
            return trimmed, False

    secret = secrets.token_urlsafe(48)
    logger.warning(
        "Generated ephemeral JWT secret; tokens will rotate on restart. "
        "Set MODACCT_JWT_SECRET_KEY or JWT_SECRET_KEY to use a persistent value."
    )
    return secret, True


def _default_jwt_secret() -> str:
    secret, ephemeral = _resolve_jwt_secret()
    _SECRET_PROVENANCE[secret] = ephemeral
    return secret


class Settings(BaseModel):
    """Application configuration derived from environment variables."""

    model_config = ConfigDict(str_strip_whitespace=True)
    _jwt_secret_is_ephemeral: bool = PrivateAttr(default=False)

    database_url: str = Field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./modacct.db")
    )
    log_level: str = Field(default_factory=lambda: os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL))
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
        default_factory=_default_jwt_secret
    )
    jwt_algorithm: str = Field(
        default_factory=lambda: os.getenv("JWT_ALGORITHM", "HS256")
    )
    access_token_expire_minutes: int = Field(
        default_factory=lambda: int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    )

    @model_validator(mode="after")
    def _normalise(self) -> "Settings":
        """Sanitise derived fields and capture secret provenance."""

        if self.jwt_secret_key in _SECRET_PROVENANCE:
            self._jwt_secret_is_ephemeral = _SECRET_PROVENANCE.pop(self.jwt_secret_key)
        return self

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: str) -> str:
        if not value:
            msg = "database_url cannot be empty"
            raise ValueError(msg)
        if "://" not in value:
            msg = "database_url must be a valid DSN"
            raise ValueError(msg)
        return value

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        level = value.upper() or DEFAULT_LOG_LEVEL
        if level not in VALID_LOG_LEVELS:
            msg = (
                "Unsupported log level '{value}'. "
                "Valid options: {levels}".format(value=value, levels=sorted(VALID_LOG_LEVELS))
            )
            raise ValueError(msg)
        return level

    @field_validator(
        "openex_app_id",
        "alphavantage_key",
        "newsapi_key",
        "gdelt_user_agent",
        mode="before",
    )
    @classmethod
    def _validate_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None

    @field_validator("jwt_secret_key")
    @classmethod
    def _validate_jwt_secret(cls, value: str) -> str:
        secret = value.strip()
        if not secret:
            msg = "jwt_secret_key cannot be empty"
            raise ValueError(msg)
        if len(secret) < 32:
            logger.warning(
                "JWT secret length %s is shorter than recommended 32 characters; consider rotating.",
                len(secret),
            )
        return secret

    @field_validator("jwt_algorithm")
    @classmethod
    def _validate_jwt_algorithm(cls, value: str) -> str:
        algorithm = value.upper()
        if algorithm not in ALLOWED_JWT_ALGORITHMS:
            msg = (
                "Unsupported JWT algorithm '{value}'. "
                "Valid options: {algorithms}".format(
                    value=value, algorithms=sorted(ALLOWED_JWT_ALGORITHMS)
                )
            )
            raise ValueError(msg)
        return algorithm

    @field_validator("access_token_expire_minutes")
    @classmethod
    def _validate_access_token_expiry(cls, value: int) -> int:
        if value <= 0:
            msg = "access_token_expire_minutes must be greater than zero"
            raise ValueError(msg)
        if value > MAX_ACCESS_TOKEN_MINUTES:
            msg = (
                "access_token_expire_minutes must not exceed {limit} minutes".format(
                    limit=MAX_ACCESS_TOKEN_MINUTES
                )
            )
            raise ValueError(msg)
        return value

    @classmethod
    def load(
        cls,
        environ: Mapping[str, str] | None = None,
        prefix: str = "MODACCT_",
        *,
        env_file: str | os.PathLike[str] | None = None,
        override_env_file: bool = False,
    ) -> "Settings":
        """Load settings from ``environ`` honoring optional ``prefix`` values."""

        if env_file is not None:
            load_dotenv(dotenv_path=Path(env_file), override=override_env_file)

        env: Mapping[str, str] = environ or os.environ

        def lookup(field: str, *aliases: str, upper: bool = False) -> str | None:
            keys = [f"{prefix}{field.upper()}", *aliases]
            for key in keys:
                if key in env and env[key] is not None:
                    value = env[key].strip()
                    if not value:
                        return None
                    return value.upper() if upper else value
            return None

        settings_data: dict[str, object] = {}
        database_url = lookup("database_url", "DATABASE_URL")
        if database_url is not None:
            settings_data["database_url"] = database_url

        log_level = lookup("log_level", "LOG_LEVEL", upper=True)
        if log_level is not None:
            settings_data["log_level"] = log_level

        optional_keys = {
            "openex_app_id": ("OPENEXCHANGERATES_APP_ID",),
            "alphavantage_key": ("ALPHAVANTAGE_API_KEY",),
            "newsapi_key": ("NEWSAPI_KEY",),
            "gdelt_user_agent": ("GDELT_USER_AGENT",),
        }

        for field_name, aliases in optional_keys.items():
            value = lookup(field_name, *aliases)
            if value is not None:
                settings_data[field_name] = value

        jwt_secret = lookup("jwt_secret_key", "JWT_SECRET_KEY")
        if jwt_secret is not None:
            settings_data["jwt_secret_key"] = jwt_secret
            _SECRET_PROVENANCE[jwt_secret] = False
        else:
            secret, ephemeral = _resolve_jwt_secret(env, prefix=prefix)
            settings_data["jwt_secret_key"] = secret
            _SECRET_PROVENANCE[secret] = ephemeral

        jwt_algorithm = lookup("jwt_algorithm", "JWT_ALGORITHM", upper=True)
        if jwt_algorithm is not None:
            settings_data["jwt_algorithm"] = jwt_algorithm

        expire_minutes = lookup("access_token_expire_minutes", "ACCESS_TOKEN_EXPIRE_MINUTES")
        if expire_minutes is not None:
            settings_data["access_token_expire_minutes"] = int(expire_minutes)

        return cls(**cast("dict[str, Any]", settings_data))

    @property
    def jwt_secret_is_ephemeral(self) -> bool:
        """True when the JWT secret was auto-generated for this process."""

        return self._jwt_secret_is_ephemeral


@lru_cache()
def get_settings() -> Settings:
    """Return an immutable :class:`Settings` instance."""

    env_file = os.getenv("MODACCT_ENV_FILE")
    if env_file:
        return Settings.load(env_file=env_file)
    return Settings.load()


settings = get_settings()
