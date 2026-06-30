from __future__ import annotations

from types import SimpleNamespace

import pytest
from apps.api.config import ExtensionInfo
from apps.api.services import extension_loader
from apps.api.services.extension_loader import (
    active_extensions,
    load_configured_extensions,
)
from apps.extensions import extension_registry


@pytest.fixture(autouse=True)
def clear_registry() -> None:
    extension_registry.clear()


def _fake_settings(**entries: ExtensionInfo) -> SimpleNamespace:
    return SimpleNamespace(allowed_extensions=entries)


def test_load_configured_extensions(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_extensions = {
        "observability:demo": ExtensionInfo(
            module="plugins.analytics_baseline.extension",
            enabled=True,
            description="Demo",
        )
    }
    monkeypatch.setattr(extension_loader, "settings", _fake_settings(**fake_extensions))

    manifests = load_configured_extensions()

    assert len(manifests) == 1
    manifest = manifests[0]
    assert manifest.key == "observability:demo"
    assert manifest.name == "Baseline Observability"


def test_active_extensions_reports_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_extensions = {
        "observability:demo": ExtensionInfo(
            module="plugins.analytics_baseline.extension",
            enabled=False,
            description="Disabled",  # intentionally disabled to exercise branch
        )
    }
    monkeypatch.setattr(extension_loader, "settings", _fake_settings(**fake_extensions))

    # Loading should skip disabled modules.
    manifests = load_configured_extensions()
    assert manifests == []

    statuses = active_extensions()
    assert len(statuses) == 1
    status = statuses[0]
    assert status.key == "observability:demo"
    assert status.module == "plugins.analytics_baseline.extension"
    assert status.enabled is False
    assert status.manifest is None


def test_extension_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_extensions = {
        "observability:demo": ExtensionInfo(
            module="plugins.analytics_baseline.extension",
            enabled=True,
        )
    }
    monkeypatch.setattr(extension_loader, "settings", _fake_settings(**fake_extensions))

    class StubTelemetry:
        def __init__(self) -> None:
            self.load_events: list[tuple[str, str]] = []
            self.enabled: dict[str, bool] = {}

        def record_load(self, *, module: str, status: str, duration: float) -> None:
            self.load_events.append((module, status))

        def set_enabled(self, *, module: str, enabled: bool) -> None:
            self.enabled[module] = enabled

    stub = StubTelemetry()
    from apps.extensions import registry as registry_module

    monkeypatch.setattr(extension_loader, "extension_telemetry", stub)
    monkeypatch.setattr(registry_module, "extension_telemetry", stub)

    manifests = load_configured_extensions()

    assert manifests
    module_path = "plugins.analytics_baseline.extension"
    assert stub.enabled[module_path] is True
    assert (module_path, "success") in stub.load_events
