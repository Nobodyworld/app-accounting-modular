from __future__ import annotations

from apps.api.config import Settings


def test_settings_reads_prefixed_environment(monkeypatch) -> None:
    monkeypatch.setenv("MODACCT_DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.setenv("LOG_LEVEL", " debug ")
    monkeypatch.setenv("NEWSAPI_KEY", "  token  ")

    cfg = Settings.load()

    assert cfg.database_url == "postgresql://user:pass@localhost/db"
    assert cfg.log_level == "debug".upper()
    assert cfg.newsapi_key == "token"


def test_settings_supports_legacy_env_names(monkeypatch) -> None:
    monkeypatch.delenv("MODACCT_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")

    cfg = Settings.load()

    assert cfg.database_url == "sqlite:///test.db"
