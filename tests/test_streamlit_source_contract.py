"""Source-level regression guards for the Streamlit presentation contract."""

from pathlib import Path


STREAMLIT_APP = Path(__file__).resolve().parents[1] / "src" / "apps" / "web" / "app.py"


def test_streamlit_app_uses_supported_width_api() -> None:
    source = STREAMLIT_APP.read_text(encoding="utf-8")

    assert "use_container_width" not in source
    assert 'width="stretch"' in source


def test_streamlit_result_details_remain_collapsed_by_default() -> None:
    source = STREAMLIT_APP.read_text(encoding="utf-8")
    expected_expanders = (
        "Forecast detail",
        "Budget report details",
        "Forecast diagnostics",
        "Cashflow report details",
        "FX synchronization details",
        "Market synchronization details",
    )

    for label in expected_expanders:
        assert f'st.expander("{label}", expanded=False)' in source
