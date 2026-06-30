from __future__ import annotations

from apps.api.config import ProviderInfo, Settings


def test_settings_load_triggers_provider_cache_refresh(monkeypatch) -> None:
    called = {"refresh": 0}

    def fake_refresh() -> None:
        called["refresh"] += 1

    monkeypatch.setenv("MODACCT_DATABASE_URL", "sqlite:///test.db")
    monkeypatch.setattr("apps.api.services.plugin_loader.refresh_provider_cache", fake_refresh)
    monkeypatch.setattr(
        "apps.api.config.DEFAULT_ALLOWED_PROVIDERS",
        {"stub": ProviderInfo(module="plugins.tax_oecd_stub.provider", name="Stub", capabilities=("tax",))},
    )

    Settings.load()

    assert called["refresh"] == 1
