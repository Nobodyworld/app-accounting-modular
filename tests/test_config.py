"""Configuration model tests validating environment parsing and defaults."""

from __future__ import annotations

import pytest

from apps.api.config import DEFAULT_LOG_FORMAT, MAX_ACCESS_TOKEN_MINUTES, Settings


def test_settings_reads_prefixed_environment(monkeypatch) -> None:
    """Settings.load should respect modern MODACCT_ prefixed environment vars."""
    monkeypatch.setenv("MODACCT_DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.setenv("LOG_LEVEL", " debug ")
    monkeypatch.setenv("NEWSAPI_KEY", "  token  ")

    cfg = Settings.load()

    assert cfg.database_url == "postgresql://user:pass@localhost/db"
    assert cfg.log_level == "debug".upper()
    assert cfg.newsapi_key == "token"
    assert cfg.log_format == DEFAULT_LOG_FORMAT


def test_settings_supports_legacy_env_names(monkeypatch) -> None:
    """Legacy env variable names should remain backwards compatible."""
    monkeypatch.delenv("MODACCT_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")

    cfg = Settings.load()

    assert cfg.database_url == "sqlite:///test.db"


def test_settings_warns_and_marks_ephemeral_secret(monkeypatch, caplog) -> None:
    """Ephemeral JWT secrets are generated with warning instrumentation."""
    monkeypatch.delenv("MODACCT_JWT_SECRET_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    caplog.set_level("WARNING", logger="apps.api.config")

    cfg = Settings.load()

    assert cfg.jwt_secret_key
    assert cfg.jwt_secret_is_ephemeral is True
    assert "Generated ephemeral JWT secret" in caplog.text


def test_settings_marks_persistent_secret(monkeypatch, caplog) -> None:
    """User-specified JWT secrets bypass ephemeral generation warnings."""
    monkeypatch.setenv("MODACCT_JWT_SECRET_KEY", "  persistent-secret  ")
    caplog.set_level("WARNING", logger="apps.api.config")

    cfg = Settings.load()

    assert cfg.jwt_secret_key == "persistent-secret"
    assert cfg.jwt_secret_is_ephemeral is False
    assert "Generated ephemeral JWT secret" not in caplog.text


def test_settings_rejects_invalid_log_level(monkeypatch) -> None:
    """Invalid log level input should raise a validation error."""
    monkeypatch.setenv("MODACCT_LOG_LEVEL", "notalevel")

    with pytest.raises(ValueError) as exc:
        Settings.load()

    assert "Unsupported log level" in str(exc.value)


def test_settings_rejects_invalid_jwt_algorithm(monkeypatch) -> None:
    """Unsupported JWT algorithms trigger descriptive validation errors."""
    monkeypatch.setenv("MODACCT_JWT_ALGORITHM", "md5")

    with pytest.raises(ValueError) as exc:
        Settings.load()

    assert "Unsupported JWT algorithm" in str(exc.value)
    assert "MD5" in str(exc.value)


def test_settings_rejects_invalid_expiry(monkeypatch) -> None:
    """Token expiries below threshold result in configuration errors."""
    monkeypatch.setenv("MODACCT_ACCESS_TOKEN_EXPIRE_MINUTES", "0")

    with pytest.raises(ValueError) as exc:
        Settings.load()

    assert "greater than zero" in str(exc.value)


# TODO - (config) Cover settings overrides for per-environment log destinations.

    monkeypatch.setenv(
        "MODACCT_ACCESS_TOKEN_EXPIRE_MINUTES",
        str(MAX_ACCESS_TOKEN_MINUTES + 1),
    )

    with pytest.raises(ValueError) as exc:
        Settings.load()

    assert "must not exceed" in str(exc.value)


def test_settings_loads_from_env_file(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "MODACCT_DATABASE_URL=postgresql://env/file\n"
        "MODACCT_LOG_LEVEL=warning\n"
        "MODACCT_LOG_FORMAT=text\n"
        "MODACCT_ACCESS_TOKEN_EXPIRE_MINUTES=120\n"
        "MODACCT_JWT_SECRET_KEY="
        "abcdefghijklmnopqrstuvwxyz012345\n"
    )
    monkeypatch.delenv("MODACCT_DATABASE_URL", raising=False)
    monkeypatch.delenv("MODACCT_LOG_LEVEL", raising=False)
    monkeypatch.delenv("MODACCT_ACCESS_TOKEN_EXPIRE_MINUTES", raising=False)
    monkeypatch.delenv("MODACCT_JWT_SECRET_KEY", raising=False)

    cfg = Settings.load(env_file=env_file)

    assert cfg.database_url == "postgresql://env/file"
    assert cfg.log_level == "WARNING"
    assert cfg.log_format == "TEXT"
    assert cfg.access_token_expire_minutes == 120
    assert cfg.jwt_secret_is_ephemeral is False


def test_settings_rejects_invalid_log_format(monkeypatch) -> None:
    monkeypatch.setenv("MODACCT_LOG_FORMAT", "yaml")

    with pytest.raises(ValueError) as exc:
        Settings.load()

    assert "JSON" in str(exc.value)
