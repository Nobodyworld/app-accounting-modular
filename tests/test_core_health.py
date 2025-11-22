from __future__ import annotations

from apps.api.routers import core


def test_provider_compatibility_summary_and_alerts() -> None:
    providers = [
        {"key": "ok", "compatibility": {"status": "compatible"}},
        {
            "key": "bad",
            "compatibility": {
                "status": "incompatible",
                "reason": "major mismatch",
                "provider_version": "1.0.0",
                "api_version": "0.0.0",
            },
        },
        {"key": "unknown"},
    ]

    summary = core._provider_compatibility_summary(providers)
    assert summary["total"] == 3
    assert summary["compatible"] == 1
    assert summary["incompatible"] == 1
    assert summary["unknown"] == 1

    alerts = core._provider_compatibility_alerts(providers)
    assert alerts == [
        {
            "provider": "bad",
            "status": "incompatible",
            "reason": "major mismatch",
            "provider_version": "1.0.0",
            "api_version": "0.0.0",
        }
    ]
