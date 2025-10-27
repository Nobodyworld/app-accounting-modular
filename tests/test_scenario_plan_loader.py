import json

import pytest

from apps.modular_accounting.application.plans import (
    ScenarioPlan,
    ScenarioPlanValidationError,
    load_plan_from_bytes,
)


def _plan_bytes(payload: dict[str, object]) -> bytes:
    return json.dumps(payload).encode("utf-8")


def test_load_plan_from_bytes_merges_defaults_and_metadata() -> None:
    payload = {
        "metadata": {
            "name": "Quarterly Metals",
            "description": "Coverage for precious metals portfolios",
            "tags": ["ops"],
            "parameters": {"owner": "treasury"},
        },
        "defaults": {
            "base_currency": "usd",
            "jurisdictions": ["US", "US-CA"],
            "tags": ["baseline"],
        },
        "scenarios": [
            {
                "name": "gold",
                "commodity_symbols": ["XAU"],
                "tags": ["precious"],
            },
            {
                "name": "silver",
                "commodity_symbols": ["XAG"],
            },
        ],
    }

    plan = load_plan_from_bytes(_plan_bytes(payload), format_hint=".json")

    assert isinstance(plan, ScenarioPlan)
    assert plan.metadata.name == "Quarterly Metals"
    assert plan.metadata.description == "Coverage for precious metals portfolios"
    assert plan.metadata.tags == ("ops",)
    assert plan.defaults["base_currency"] == "USD"
    assert plan.defaults["jurisdictions"] == ["US", "US-CA"]
    assert plan.scenarios[0].name == "gold"
    assert plan.scenarios[0].tags == ("ops", "baseline", "precious")
    assert plan.scenarios[1].tags == ("ops", "baseline")


def test_plan_summary_reports_unique_assets() -> None:
    payload = {
        "metadata": {"name": "FX Coverage", "tags": ["fx"]},
        "defaults": {"base_currency": "USD"},
        "scenarios": [
            {"name": "usd_fx", "commodity_symbols": [], "jurisdictions": None},
            {
                "name": "eur_fx",
                "base_currency": "EUR",
                "commodity_symbols": [],
                "tags": ["emea"],
            },
        ],
    }

    plan = load_plan_from_bytes(_plan_bytes(payload), format_hint=".json")
    summary = plan.summary()

    assert summary.scenario_count == 2
    assert set(summary.base_currencies) == {"USD", "EUR"}
    assert summary.commodity_symbols == ()
    assert summary.defaults_applied == ("base_currency",)
    assert summary.tag_counts == {"fx": 2, "emea": 1}


def test_duplicate_scenario_names_raise_validation_error() -> None:
    payload = {
        "metadata": {"name": "Invalid"},
        "scenarios": [
            {"name": "dup", "base_currency": "USD"},
            {"name": "dup", "base_currency": "EUR"},
        ],
    }

    with pytest.raises(ScenarioPlanValidationError):
        load_plan_from_bytes(_plan_bytes(payload), format_hint=".json")


def test_plan_normalises_byte_tags() -> None:
    plan = ScenarioPlan.from_components(
        name="Bytes everywhere",
        tags=[b"ops", b"ops"],
        defaults={
            "base_currency": "usd",
            "tags": [b"default", " default "],
        },
        scenarios=[
            {
                "name": "case",
                "base_currency": "usd",
                "commodity_symbols": ["xau"],
                "tags": [b"special", b"special"],
            }
        ],
    )

    assert plan.metadata.tags == ("ops",)
    assert plan.defaults["tags"] == ["default"]
    assert plan.scenarios[0].tags == ("ops", "default", "special")


def test_plan_defaults_reject_non_string_base_currency() -> None:
    with pytest.raises(ScenarioPlanValidationError):
        ScenarioPlan.from_components(
            name="Invalid",
            defaults={"base_currency": 123},
            scenarios=[{"name": "only", "base_currency": "USD"}],
        )


def test_plan_defaults_decode_byte_base_currency() -> None:
    plan = ScenarioPlan.from_components(
        name="Decode defaults",
        defaults={"base_currency": b"usd"},
        scenarios=[{"name": "only", "commodity_symbols": []}],
    )

    assert plan.defaults["base_currency"] == "USD"
    assert plan.scenarios[0].base_currency == "USD"


def test_plan_defaults_normalise_sequence_bytes() -> None:
    plan = ScenarioPlan.from_components(
        name="Sequence defaults",
        defaults={
            "commodity_symbols": [b"xau", " XAG "],
            "jurisdictions": b"us ",
        },
        scenarios=[{"name": "seq", "base_currency": "USD"}],
    )

    assert plan.defaults["commodity_symbols"] == ["xau", "XAG"]
    assert plan.defaults["jurisdictions"] == ["us"]
    assert plan.scenarios[0].commodity_symbols == ("XAU", "XAG")
    assert plan.scenarios[0].jurisdictions == ("us",)
