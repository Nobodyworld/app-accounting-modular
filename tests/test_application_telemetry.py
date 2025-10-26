"""Tests for the application-level telemetry shim."""

from __future__ import annotations

import sys
import types

import pytest

from apps.modular_accounting.application import telemetry_provider


def _reset_cache() -> None:
    telemetry_provider.cache_clear()


def test_telemetry_provider_returns_none_when_metrics_missing():
    """The provider should tolerate import errors and fall back to ``None``."""

    _reset_cache()
    original = sys.modules.pop("apps.observability.metrics", None)
    placeholder = types.ModuleType("apps.observability.metrics")
    sys.modules["apps.observability.metrics"] = placeholder
    try:
        assert telemetry_provider() is None
    finally:
        _reset_cache()
        sys.modules.pop("apps.observability.metrics", None)
        if original is not None:
            sys.modules["apps.observability.metrics"] = original


def test_telemetry_provider_returns_snapshot_adapter():
    """When the observability package is present the adapter is returned."""

    _reset_cache()
    module = types.ModuleType("apps.observability.metrics")
    sentinel = object()
    module.snapshot_telemetry = sentinel  # type: ignore[attr-defined]
    original = sys.modules.pop("apps.observability.metrics", None)
    sys.modules["apps.observability.metrics"] = module
    try:
        assert telemetry_provider() is sentinel

        # Subsequent calls should hit the cache without re-importing the module.
        module.snapshot_telemetry = object()  # type: ignore[attr-defined]
        assert telemetry_provider() is sentinel
    finally:
        _reset_cache()
        sys.modules.pop("apps.observability.metrics", None)
        if original is not None:
            sys.modules["apps.observability.metrics"] = original


def test_telemetry_provider_propagates_unexpected_errors():
    """Unexpected import errors should bubble up to alert operators."""

    _reset_cache()
    original = sys.modules.pop("apps.observability.metrics", None)

    failing_module = types.ModuleType("apps.observability.metrics")

    def _raise_runtime_error(name: str) -> None:
        raise RuntimeError("boom")

    failing_module.__getattr__ = _raise_runtime_error  # type: ignore[attr-defined]
    sys.modules["apps.observability.metrics"] = failing_module
    try:
        with pytest.raises(RuntimeError):
            telemetry_provider()
    finally:
        _reset_cache()
        sys.modules.pop("apps.observability.metrics", None)

    sentinel = object()
    healthy_module = types.ModuleType("apps.observability.metrics")
    healthy_module.snapshot_telemetry = sentinel  # type: ignore[attr-defined]
    sys.modules["apps.observability.metrics"] = healthy_module
    try:
        assert telemetry_provider() is sentinel
    finally:
        _reset_cache()
        sys.modules.pop("apps.observability.metrics", None)
        if original is not None:
            sys.modules["apps.observability.metrics"] = original
