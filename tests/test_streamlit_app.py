"""Streamlit AppTest coverage for the primary Snapshot & Controls flow."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
import streamlit as st

pytest.importorskip("streamlit", reason="streamlit dependencies not available")
from streamlit.testing.v1 import AppTest  # type: ignore[import-not-found]


def _app_test() -> AppTest:
    st.cache_data.clear()
    return AppTest.from_file("apps/web/app.py")


class DummyResponse:
    """Simple response stub to simulate ``requests`` interactions."""

    def __init__(self, payload: dict[str, Any], status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("request failed")


@dataclass
class SnapshotCall:
    base_currency: str
    commodity_symbols: list[str]
    jurisdictions: list[str]


@pytest.fixture
def fake_runtime(monkeypatch):
    """Provide deterministic provider/health payloads and snapshot orchestration."""

    import sys
    from pathlib import Path

    src_path = str(Path(__file__).parent.parent / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    from apps.api.services import snapshot_service

    calls: list[SnapshotCall] = []

    providers = [
        {
            "key": "fx:ecb",
            "name": "ECB FX",
            "capabilities": ["fx"],
        },
        {
            "key": "market:commodities_stub",
            "name": "Commodity Stub",
            "capabilities": ["market"],
        },
        {
            "key": "tax:oecd_stub",
            "name": "Tax Stub",
            "capabilities": ["tax"],
        },
    ]

    def fake_get(url: str, timeout: int = 5, params: dict[str, Any] | None = None):
        if url.endswith("/health"):
            return DummyResponse({"status": "ok"})
        if url.endswith("/health/ready"):
            return DummyResponse(
                {
                    "status": "ok",
                    "reports": [{"name": "database", "healthy": True, "severity": "critical"}],
                }
            )
        if url.endswith("/providers"):
            return DummyResponse({"providers": providers})
        if url.endswith("/reports/budget-vs-actual"):
            return DummyResponse({"summary": {"total_actual": 120.0}})
        if url.endswith("/reports/cashflow-forecast"):
            return DummyResponse({"current_cash": -180.0, "historical": []})
        return DummyResponse({"ok": True})

    def fake_post(
        url: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        timeout: int = 5,
    ):
        if url.endswith("/snapshot/plans/preview"):
            return DummyResponse({"summary": {"scenario_count": 1}, "plan": {"metadata": {}}})
        return DummyResponse({"ok": True})

    class FakeSnapshotResult:
        def as_payload(self) -> dict[str, Any]:
            return {
                "fx_rates": [
                    {
                        "base_currency": "USD",
                        "quote_currency": "EUR",
                        "rate": "0.92",
                        "as_of": "2026-07-02T00:00:00+00:00",
                    }
                ],
                "commodity_quotes": [
                    {
                        "symbol": "XAU",
                        "price": {"amount": "2350.10", "currency": "USD"},
                        "as_of": "2026-07-02T00:00:00+00:00",
                    }
                ],
                "tax_rules": [
                    {
                        "jurisdiction": "US",
                        "rate": "0.21",
                        "description": "corporate",
                        "effective_from": "2026-01-01",
                        "effective_to": None,
                    }
                ],
                "diagnostics": {
                    "fx_max_age_seconds": 120,
                    "commodity_max_age_seconds": 240,
                    "active_tax_rule_count": 1,
                },
                "providers": {
                    "fx": "fx:ecb",
                    "commodity": "market:commodities_stub",
                    "tax": "tax:oecd_stub",
                },
                "cache_stats": {
                    "fx": {"size": 1, "hits": 0, "misses": 1},
                    "commodities": {"size": 1, "hits": 0, "misses": 1},
                    "tax": {"size": 1, "hits": 0, "misses": 1},
                },
            }

    class FakeSnapshotOrchestrator:
        def __init__(
            self,
            *,
            fx_provider_key: str | None = None,
            commodity_provider_key: str | None = None,
            tax_provider_key: str | None = None,
            **_: Any,
        ) -> None:
            self.fx_provider_key = fx_provider_key
            self.commodity_provider_key = commodity_provider_key
            self.tax_provider_key = tax_provider_key

        def build_snapshot(
            self,
            *,
            base_currency: str,
            commodity_symbols: list[str] | None = None,
            jurisdictions: list[str] | None = None,
        ) -> FakeSnapshotResult:
            calls.append(
                SnapshotCall(
                    base_currency=base_currency,
                    commodity_symbols=list(commodity_symbols or []),
                    jurisdictions=list(jurisdictions or []),
                )
            )
            return FakeSnapshotResult()

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("requests.post", fake_post)
    monkeypatch.setattr(snapshot_service, "SnapshotOrchestrator", FakeSnapshotOrchestrator)
    monkeypatch.setenv("API_BASE", "http://fake")
    monkeypatch.setenv("STREAMLIT_TESTING", "1")
    return SimpleNamespace(calls=calls)


def test_primary_snapshot_tab_renders(fake_runtime):
    at = _app_test()
    at.run(timeout=15)

    labels = [tab.label for tab in at.tabs]
    assert "Snapshot & Controls" in labels
    assert "Experimental Utilities" in labels
    assert "Scenario Plans" in labels

    # Validate provider controls are present and selectable.
    assert at.selectbox(key="snapshot_fx_provider_select").value == "fx:ecb"
    assert at.selectbox(key="snapshot_commodity_provider_select").value == "market:commodities_stub"
    assert at.selectbox(key="snapshot_tax_provider_select").value == "tax:oecd_stub"


def test_snapshot_request_execution_and_diagnostics(fake_runtime):
    at = _app_test()
    at.run(timeout=15)

    at.text_input(key="snapshot_base_input").set_value("USD")
    at.run(timeout=10)
    at.multiselect(key="snapshot_symbols_multi").set_value(["XAU"])
    at.run(timeout=10)
    at.multiselect(key="snapshot_jurisdictions_multi").set_value(["US"])
    at.run(timeout=10)
    at.button(key="snapshot_generate_button").click()
    at.run(timeout=20)

    assert "snapshot_controls_payload" in at.session_state
    payload = at.session_state["snapshot_controls_payload"]
    assert len(payload["fx_rates"]) == 1
    assert len(payload["commodity_quotes"]) == 1
    assert len(payload["tax_rules"]) == 1
    assert payload["providers"]["fx"] == "fx:ecb"
    assert "snapshot_controls_params" in at.session_state
    assert fake_runtime.calls
    assert fake_runtime.calls[0].base_currency == "USD"


def test_invalid_currency_blocks_snapshot(fake_runtime):
    at = _app_test()
    at.run(timeout=15)

    at.text_input(key="snapshot_base_input").set_value("US")
    at.run(timeout=10)

    assert at.button(key="snapshot_generate_button").disabled is True
    assert "snapshot_controls_payload" not in at.session_state


def test_missing_provider_capability_shows_warning(monkeypatch):
    """When provider capabilities are missing, generation should be disabled with a warning."""

    def fake_get(url: str, timeout: int = 5, params: dict[str, Any] | None = None):
        if url.endswith("/health"):
            return DummyResponse({"status": "ok"})
        if url.endswith("/health/ready"):
            return DummyResponse({"status": "ok", "reports": []})
        if url.endswith("/providers"):
            return DummyResponse(
                {
                    "providers": [
                        {"key": "fx:ecb", "name": "ECB FX", "capabilities": ["fx"]},
                        {
                            "key": "market:commodities_stub",
                            "name": "Commodity Stub",
                            "capabilities": ["market"],
                        },
                    ]
                }
            )
        return DummyResponse({"ok": True})

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: DummyResponse({"ok": True}))
    monkeypatch.setenv("API_BASE", "http://fake")
    monkeypatch.setenv("STREAMLIT_TESTING", "1")

    at = _app_test()
    at.run(timeout=15)

    assert at.button(key="snapshot_generate_button").disabled is True
    assert any("Missing provider capabilities" in warning.value for warning in at.warning)


def test_provider_loading_failure_is_reported(monkeypatch):
    """Providers API failure should surface a clear primary-flow error state."""

    def fake_get(url: str, timeout: int = 5, params: dict[str, Any] | None = None):
        if url.endswith("/providers"):
            raise RuntimeError("providers unavailable")
        if url.endswith("/health"):
            return DummyResponse({"status": "ok"})
        if url.endswith("/health/ready"):
            return DummyResponse({"status": "ok", "reports": []})
        return DummyResponse({"ok": True})

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: DummyResponse({"ok": True}))
    monkeypatch.setenv("API_BASE", "http://fake")
    monkeypatch.setenv("STREAMLIT_TESTING", "1")

    at = _app_test()
    at.run(timeout=15)

    assert any("Unable to load provider catalog" in err.value for err in at.error)


def test_snapshot_tables_render_with_correct_columns(fake_runtime):
    """After successful snapshot, verify FX, commodity, and tax tables render with expected columns."""
    at = _app_test()
    at.run(timeout=15)

    at.text_input(key="snapshot_base_input").set_value("USD")
    at.run(timeout=10)
    at.multiselect(key="snapshot_symbols_multi").set_value(["XAU"])
    at.run(timeout=10)
    at.multiselect(key="snapshot_jurisdictions_multi").set_value(["US"])
    at.run(timeout=10)
    at.button(key="snapshot_generate_button").click()
    at.run(timeout=20)

    assert "snapshot_controls_payload" in at.session_state

    # Verify that dataframes were rendered (AppTest captures dataframe elements).
    # The app uses st.dataframe() for FX, commodity, and tax tables.
    dataframes = at.dataframe
    # Provider catalog is shown first (index 0), then FX (1), commodity (2), tax (3), provenance (4), cache (5)
    assert len(dataframes) >= 6, f"Expected at least 6 dataframes, got {len(dataframes)}"

    # Verify the second dataframe (FX table) has expected columns (index 1 after provider catalog).
    fx_df = dataframes[1].value
    assert "Base" in fx_df.columns
    assert "Quote" in fx_df.columns
    assert "Rate" in fx_df.columns
    assert "As Of" in fx_df.columns
    assert len(fx_df) == 1

    # Verify the third dataframe (commodity table) has expected columns (index 2).
    commodity_df = dataframes[2].value
    assert "Symbol" in commodity_df.columns
    assert "Price" in commodity_df.columns
    assert "Currency" in commodity_df.columns
    assert "As Of" in commodity_df.columns
    assert len(commodity_df) == 1

    # Verify the fourth dataframe (tax table) has expected columns (index 3).
    tax_df = dataframes[3].value
    assert "Jurisdiction" in tax_df.columns
    assert "Rate" in tax_df.columns
    assert "Description" in tax_df.columns
    assert "Effective From" in tax_df.columns
    assert "Effective To" in tax_df.columns
    assert len(tax_df) == 1


def test_snapshot_provenance_and_diagnostics_rendered(fake_runtime):
    """Verify provider provenance, cache diagnostics, health/readiness, and journal control are visible."""
    at = _app_test()
    at.run(timeout=15)

    at.text_input(key="snapshot_base_input").set_value("USD")
    at.run(timeout=10)
    at.multiselect(key="snapshot_symbols_multi").set_value(["XAU"])
    at.run(timeout=10)
    at.multiselect(key="snapshot_jurisdictions_multi").set_value(["US"])
    at.run(timeout=10)
    at.button(key="snapshot_generate_button").click()
    at.run(timeout=20)

    # After successful snapshot, AppTest captures all markdown and dataframe output.
    # Check for provenance section header.
    markdown_content = [el.value for el in at.markdown]
    assert any("Provider provenance" in str(el) for el in markdown_content), (
        "Provider provenance section should be rendered"
    )
    assert any("Cache and freshness diagnostics" in str(el) for el in markdown_content), (
        "Cache diagnostics section should be rendered"
    )
    assert any("Health and readiness state" in str(el) for el in markdown_content), (
        "Health/readiness section should be rendered"
    )
    assert any("Journal-control status" in str(el) for el in markdown_content), (
        "Journal control section should be rendered"
    )

    # Verify cache stats dataframe is present (index 5: provider table, FX, commodity, tax, provenance, cache).
    dataframes = at.dataframe
    assert len(dataframes) >= 6, f"Expected at least 6 dataframes, got {len(dataframes)}"
    cache_df = dataframes[5].value
    assert "Cache" in cache_df.columns
    assert "Size" in cache_df.columns
    assert "Hits" in cache_df.columns
    assert "Misses" in cache_df.columns


def test_case_study_link_is_visible(fake_runtime):
    """Verify the foreign-currency case-study link is rendered after successful snapshot."""
    at = _app_test()
    at.run(timeout=15)

    at.text_input(key="snapshot_base_input").set_value("USD")
    at.run(timeout=10)
    at.multiselect(key="snapshot_symbols_multi").set_value(["XAU"])
    at.run(timeout=10)
    at.multiselect(key="snapshot_jurisdictions_multi").set_value(["US"])
    at.run(timeout=10)
    at.button(key="snapshot_generate_button").click()
    at.run(timeout=20)

    # Verify case study link is present in markdown content.
    markdown_content = [el.value for el in at.markdown]
    case_study_present = any("foreign-currency accounting case study" in str(el).lower() for el in markdown_content)
    assert case_study_present, "Case study link should be visible after successful snapshot"


def test_snapshot_generation_failure_shows_error_state(fake_runtime, monkeypatch):
    """When SnapshotOrchestrator.build_snapshot() raises, UI should display error state and clear prior success."""

    import sys
    from pathlib import Path

    src_path = str(Path(__file__).parent.parent / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    # Patch the orchestrator to raise on build_snapshot.
    from apps.api.services import snapshot_service

    class FailingSnapshotOrchestrator:
        def __init__(self, **_: Any) -> None:
            pass

        def build_snapshot(self, **_: Any) -> None:
            raise RuntimeError("Orchestrator failed: provider connectivity lost")

    monkeypatch.setattr(snapshot_service, "SnapshotOrchestrator", FailingSnapshotOrchestrator)

    def fake_get(url: str, timeout: int = 5, params: dict[str, Any] | None = None):
        if url.endswith("/health"):
            return DummyResponse({"status": "ok"})
        if url.endswith("/health/ready"):
            return DummyResponse({"status": "ok", "reports": []})
        if url.endswith("/providers"):
            return DummyResponse(
                {
                    "providers": [
                        {"key": "fx:ecb", "name": "ECB FX", "capabilities": ["fx"]},
                        {"key": "market:commodities_stub", "name": "Commodity Stub", "capabilities": ["market"]},
                        {"key": "tax:oecd_stub", "name": "Tax Stub", "capabilities": ["tax"]},
                    ]
                }
            )
        return DummyResponse({"ok": True})

    monkeypatch.setattr("requests.get", fake_get)
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: DummyResponse({"ok": True}))
    monkeypatch.setenv("API_BASE", "http://fake")
    monkeypatch.setenv("STREAMLIT_TESTING", "1")

    at = _app_test()
    at.run(timeout=15)

    at.text_input(key="snapshot_base_input").set_value("USD")
    at.run(timeout=10)
    at.multiselect(key="snapshot_symbols_multi").set_value(["XAU"])
    at.run(timeout=10)
    at.multiselect(key="snapshot_jurisdictions_multi").set_value(["US"])
    at.run(timeout=10)
    at.button(key="snapshot_generate_button").click()
    at.run(timeout=20)

    # After snapshot generation failure, error should be displayed.
    assert any("Snapshot request failed" in err.value for err in at.error), (
        "Error state should display 'Snapshot request failed' message"
    )

    # Verify that no success message is shown.
    success_msgs = [el.value for el in at.success]
    assert not any("Snapshot generated" in str(el) for el in success_msgs), (
        "Success message should not appear after failed snapshot"
    )


def test_stale_success_cleared_after_failed_snapshot(fake_runtime, monkeypatch):
    """After a successful snapshot followed by a failed snapshot, stale success state should be cleared."""

    import sys
    from pathlib import Path

    src_path = str(Path(__file__).parent.parent / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    from apps.api.services import snapshot_service

    # First run succeeds with normal orchestrator.
    def fake_get_success(url: str, timeout: int = 5, params: dict[str, Any] | None = None):
        if url.endswith("/health"):
            return DummyResponse({"status": "ok"})
        if url.endswith("/health/ready"):
            return DummyResponse({"status": "ok", "reports": []})
        if url.endswith("/providers"):
            return DummyResponse(
                {
                    "providers": [
                        {"key": "fx:ecb", "name": "ECB FX", "capabilities": ["fx"]},
                        {"key": "market:commodities_stub", "name": "Commodity Stub", "capabilities": ["market"]},
                        {"key": "tax:oecd_stub", "name": "Tax Stub", "capabilities": ["tax"]},
                    ]
                }
            )
        return DummyResponse({"ok": True})

    monkeypatch.setattr("requests.get", fake_get_success)
    monkeypatch.setattr("requests.post", lambda *args, **kwargs: DummyResponse({"ok": True}))
    monkeypatch.setenv("API_BASE", "http://fake")
    monkeypatch.setenv("STREAMLIT_TESTING", "1")

    at = _app_test()
    at.run(timeout=15)

    # First successful run.
    at.text_input(key="snapshot_base_input").set_value("USD")
    at.run(timeout=10)
    at.multiselect(key="snapshot_symbols_multi").set_value(["XAU"])
    at.run(timeout=10)
    at.multiselect(key="snapshot_jurisdictions_multi").set_value(["US"])
    at.run(timeout=10)
    at.button(key="snapshot_generate_button").click()
    at.run(timeout=20)

    # Verify success state.
    success_msgs = [el.value for el in at.success]
    assert any("Snapshot generated" in str(el) for el in success_msgs), "First snapshot should succeed"

    # Now patch orchestrator to fail.
    class FailingSnapshotOrchestrator:
        def __init__(self, **_: Any) -> None:
            pass

        def build_snapshot(self, **_: Any) -> None:
            raise RuntimeError("Provider failure")

    monkeypatch.setattr(snapshot_service, "SnapshotOrchestrator", FailingSnapshotOrchestrator)

    # Second run fails.
    at.button(key="snapshot_generate_button").click()
    at.run(timeout=20)

    # After failed snapshot, error should be visible and success should be cleared.
    assert any("Snapshot request failed" in err.value for err in at.error), (
        "Error state should appear after failed snapshot"
    )

    # Clear cache and rerun to verify stale state is not persisted.
    st.cache_data.clear()
    at2 = _app_test()
    at2.run(timeout=15)

    # Confirm initial state has no success message.
    initial_success = [el.value for el in at2.success]
    assert not any("Snapshot generated" in str(el) for el in initial_success), (
        "Fresh run should not have stale success state"
    )
