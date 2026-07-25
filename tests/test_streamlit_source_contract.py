"""Source-level regression guards for the Streamlit presentation contract."""

from pathlib import Path

STREAMLIT_APP = Path(__file__).resolve().parents[1] / "src" / "apps" / "web" / "app.py"


def test_streamlit_app_uses_supported_width_api() -> None:
    source = STREAMLIT_APP.read_text(encoding="utf-8")

    assert "use_container_width" not in source
    assert 'width="stretch"' in source


def test_streamlit_result_details_remain_collapsed_by_default() -> None:
    source = STREAMLIT_APP.read_text(encoding="utf-8")
    direct_expanders = (
        "Forecast detail",
        "Budget report details",
        "Forecast diagnostics",
        "Cashflow report details",
    )
    shared_detail_labels = (
        "FX synchronization details",
        "Market synchronization details",
    )

    for label in direct_expanders:
        assert f'st.expander("{label}", expanded=False)' in source
    assert "st.expander(details_label, expanded=False)" in source
    for label in shared_detail_labels:
        assert f'details_label="{label}"' in source


def test_disabled_protected_actions_explain_their_blocker() -> None:
    source = STREAMLIT_APP.read_text(encoding="utf-8")

    assert source.count("help=protected_action_help") == 2
    assert "help=fx_action_help" in source
    assert "help=market_action_help" in source
    assert "help=scenario_action_help" in source
    assert "Configure an FX provider before synchronizing rates." in source
    assert "Configure a market provider before synchronizing prices." in source
    assert "Enter a market symbol before synchronizing prices." in source


def test_result_metrics_use_two_column_rows_for_responsive_readability() -> None:
    source = STREAMLIT_APP.read_text(encoding="utf-8")

    assert "for row_start in range(0, len(metrics), 2):" in source
    assert "st.columns(len(row_metrics))" in source
    assert source.count("_render_result_metrics(") == 4
    assert "count_column, provider_column, organization_column = st.columns(3)" not in source


def test_budget_forecast_details_are_serialized_for_arrow_compatibility() -> None:
    source = STREAMLIT_APP.read_text(encoding="utf-8")

    assert '"Forecast": json.dumps(row["Forecast"], default=str, ensure_ascii=False)' in source
