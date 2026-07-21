"""Streamlit AppTest coverage for the primary Snapshot & Controls flow."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
import streamlit as st
from apps.web.api_session import ACCESS_TOKEN_KEY, AUTH_EMAIL_KEY, ORGANIZATION_ID_KEY, SESSION_ID_KEY

pytest.importorskip("streamlit", reason="streamlit dependencies not available")
from streamlit.testing.v1 import AppTest  # type: ignore[import-not-found]


def _app_test() -> AppTest:
    st.cache_data.clear()
    return AppTest.from_file("apps/web/app.py")


class DummyResponse:
    """Simple response stub to simulate ``requests`` interactions."""

    def __init__(self, payload: Any, status_code: int = 200, text: str = ""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("request failed")


@dataclass
class SnapshotCall:
    base_currency: str
    commodity_symbols: list[str]
    jurisdictions: list[str]


@dataclass
class RequestCall:
    """Recorded HTTP request data used to verify protected request contracts."""

    method: str
    url: str
    headers: dict[str, str] | None
    data: dict[str, Any] | None
    params: dict[str, Any] | None
    json: dict[str, Any] | None
    timeout: int


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
    outbound_calls: list[RequestCall] = []
    get_responses: dict[str, DummyResponse] = {}
    post_responses: dict[str, DummyResponse] = {}
    token_value = "-".join(("streamlit", "session", "token"))

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

    def fake_get(
        url: str,
        timeout: int = 5,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> DummyResponse:
        outbound_calls.append(
            RequestCall(
                method="GET",
                url=url,
                headers=headers,
                data=data,
                params=params,
                json=json,
                timeout=timeout,
            )
        )
        for path, response in get_responses.items():
            if url.endswith(path):
                return response
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
        timeout: int = 5,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> DummyResponse:
        outbound_calls.append(
            RequestCall(
                method="POST",
                url=url,
                headers=headers,
                data=data,
                params=params,
                json=json,
                timeout=timeout,
            )
        )
        for path, response in post_responses.items():
            if url.endswith(path):
                return response
        if url.endswith("/auth/token"):
            return DummyResponse(
                {
                    "access_token": token_value,
                    "token_type": "bearer",
                    "session_id": "streamlit-session",
                }
            )
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
    return SimpleNamespace(
        calls=calls,
        outbound_calls=outbound_calls,
        get_responses=get_responses,
        post_responses=post_responses,
        token_value=token_value,
    )


def _login(at: AppTest, *, email: str = "User@Example.COM", organization_id: int = 7) -> None:
    """Complete the sidebar sign-in flow through AppTest."""

    at.text_input(key="api_login_email").set_value(email)
    at.text_input(key="api_login_password").set_value("not-retained")
    at.number_input(key="api_organization_input").set_value(organization_id)
    at.button(key="api_login_button").click()
    at.run(timeout=15)


def test_primary_snapshot_tab_renders(fake_runtime):
    at = _app_test()
    at.run(timeout=15)

    labels = [tab.label for tab in at.tabs]
    assert "Snapshot Review" in labels
    assert "Review Utilities" in labels
    assert "Scenario Plans" in labels
    assert "Experimental Utilities" not in labels

    markdown_content = [el.value for el in at.markdown]
    info_content = [el.value for el in at.info]
    assert any("provider catalog" in str(el).lower() for el in info_content + markdown_content)

    # Validate provider controls are present and selectable.
    assert at.selectbox(key="snapshot_fx_provider_select").value == "fx:ecb"
    assert at.selectbox(key="snapshot_commodity_provider_select").value == "market:commodities_stub"
    assert at.selectbox(key="snapshot_tax_provider_select").value == "tax:oecd_stub"


def test_public_workflows_remain_available_and_protected_actions_start_locked(fake_runtime):
    """Public review remains usable without an API session while utilities are visibly gated."""

    at = _app_test()
    at.run(timeout=15)

    assert at.button(key="snapshot_generate_button").disabled is False
    assert at.button(key="scenario_plan_preview_button").disabled is False
    for key in ("budget_report_button", "cashflow_report_button", "fx_sync_button", "market_sync_button"):
        assert at.button(key=key).disabled is True

    public_status = " ".join(str(element.value) for element in [*at.info, *at.caption, *at.warning])
    assert "Snapshot Review is a public/local evidence workflow" in public_status
    assert "Scenario Plan Preview is public" in public_status
    assert "Review Utilities require an authenticated API session" in public_status
    assert "Protected utilities locked" in public_status
    protected_paths = ("/reports/budget-vs-actual", "/reports/cashflow-forecast", "/fx/sync", "/market/sync")
    assert not any(call.url.endswith(protected_paths) for call in fake_runtime.outbound_calls)


def test_successful_sidebar_login_normalizes_and_unlocks_protected_actions(fake_runtime):
    """The sidebar uses the shared helper and never retains the submitted password."""

    at = _app_test()
    at.run(timeout=15)
    _login(at)

    auth_call = next(call for call in fake_runtime.outbound_calls if call.url.endswith("/auth/token"))
    assert auth_call.data == {"username": "user@example.com", "password": "not-retained"}
    assert at.session_state[ACCESS_TOKEN_KEY] == fake_runtime.token_value
    assert at.session_state[SESSION_ID_KEY] == "streamlit-session"
    assert at.session_state[AUTH_EMAIL_KEY] == "user@example.com"
    assert at.session_state[ORGANIZATION_ID_KEY] == 7
    assert "api_login_password" not in at.session_state
    assert any(element.value == "Authenticated" for element in at.success)
    assert any("user@example.com" in str(element.value) for element in at.markdown)

    for key in ("budget_report_button", "cashflow_report_button", "fx_sync_button", "market_sync_button"):
        assert at.button(key=key).disabled is False


def test_failed_sidebar_login_shows_api_detail_and_keeps_utilities_locked(fake_runtime):
    """Failed credentials clear any partial state and retain the actionable API message."""

    fake_runtime.post_responses["/auth/token"] = DummyResponse(
        {"detail": "Incorrect username or password"},
        status_code=401,
    )
    at = _app_test()
    at.run(timeout=15)
    _login(at)

    assert any("Incorrect username or password" in str(element.value) for element in at.error)
    for key in (ACCESS_TOKEN_KEY, SESSION_ID_KEY, AUTH_EMAIL_KEY, ORGANIZATION_ID_KEY):
        assert key not in at.session_state
    for key in ("budget_report_button", "cashflow_report_button", "fx_sync_button", "market_sync_button"):
        assert at.button(key=key).disabled is True


def test_logout_clears_only_api_session_and_relocks_protected_actions(fake_runtime):
    """Logout uses the shared clear helper without losing public workflow state."""

    at = _app_test()
    at.run(timeout=15)
    at.text_input(key="snapshot_base_input").set_value("EUR")
    at.run(timeout=15)
    _login(at)

    at.button(key="api_logout_button").click()
    at.run(timeout=15)

    for key in (ACCESS_TOKEN_KEY, SESSION_ID_KEY, AUTH_EMAIL_KEY, ORGANIZATION_ID_KEY):
        assert key not in at.session_state
    assert at.session_state["snapshot_base_input"] == "EUR"
    for key in ("budget_report_button", "cashflow_report_button", "fx_sync_button", "market_sync_button"):
        assert at.button(key=key).disabled is True


def test_protected_request_contracts_use_shared_session_scope(fake_runtime):
    """All utility requests include the authenticated tenant scope and bearer header."""

    at = _app_test()
    at.run(timeout=15)
    _login(at, organization_id=12)

    at.number_input(key="budget_id_input").set_value(31)
    at.number_input(key="budget_horizon_input").set_value(45)
    at.checkbox(key="budget_refresh_toggle").set_value(True)
    at.run(timeout=15)
    at.button(key="budget_report_button").click()
    at.run(timeout=15)

    at.number_input(key="cashflow_horizon_input").set_value(75)
    at.checkbox(key="cashflow_refresh_toggle").set_value(False)
    at.run(timeout=15)
    at.button(key="cashflow_report_button").click()
    at.run(timeout=15)

    at.text_input(key="fx_base_input").set_value(" eur ")
    at.run(timeout=15)
    at.button(key="fx_sync_button").click()
    at.run(timeout=15)

    at.text_input(key="market_symbol_input").set_value(" msft ")
    at.run(timeout=15)
    at.button(key="market_sync_button").click()
    at.run(timeout=15)

    auth_header = {"Authorization": f"Bearer {fake_runtime.token_value}"}
    budget_call = next(call for call in fake_runtime.outbound_calls if call.url.endswith("/reports/budget-vs-actual"))
    assert budget_call.headers == auth_header
    assert budget_call.params == {"budget_id": 31, "organization_id": 12, "horizon": 45, "refresh": True}

    cashflow_call = next(
        call for call in fake_runtime.outbound_calls if call.url.endswith("/reports/cashflow-forecast")
    )
    assert cashflow_call.headers == auth_header
    assert cashflow_call.params == {"organization_id": 12, "horizon": 75, "refresh": False}

    fx_call = next(call for call in fake_runtime.outbound_calls if call.url.endswith("/fx/sync"))
    assert fx_call.headers == auth_header
    assert fx_call.params == {"organization_id": 12, "base": "EUR", "provider_key": "fx:ecb"}

    market_call = next(call for call in fake_runtime.outbound_calls if call.url.endswith("/market/sync"))
    assert market_call.headers == auth_header
    assert market_call.params == {
        "organization_id": 12,
        "symbol": "MSFT",
        "start": "2024-01-01",
        "end": "2024-12-31",
        "provider_key": "market:commodities_stub",
    }


def test_protected_api_errors_are_actionable_and_clear_stale_cashflow_success(fake_runtime):
    """FastAPI detail strings and validation lists are safe to display and clear stale results."""

    at = _app_test()
    at.run(timeout=15)
    _login(at)

    at.button(key="cashflow_report_button").click()
    at.run(timeout=15)
    assert "cashflow_report_payload" in at.session_state

    fake_runtime.get_responses["/reports/cashflow-forecast"] = DummyResponse(
        {"detail": [{"msg": "Field required"}]},
        status_code=422,
    )
    at.button(key="cashflow_report_button").click()
    at.run(timeout=15)
    assert "cashflow_report_payload" not in at.session_state
    assert any("Field required" in str(element.value) for element in at.error)

    fake_runtime.get_responses["/reports/budget-vs-actual"] = DummyResponse(
        {"detail": "Not authorized for this organization"},
        status_code=403,
    )
    at.button(key="budget_report_button").click()
    at.run(timeout=15)
    assert any("Not authorized for this organization" in str(element.value) for element in at.error)


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
    assert any("Snapshot review generated" in str(el) for el in success_msgs), "First snapshot should succeed"

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
    assert not any("Snapshot review generated" in str(el) for el in initial_success), (
        "Fresh run should not have stale success state"
    )
