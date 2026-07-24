"""Focused API-schema contracts for scenario-plan defaults."""

from __future__ import annotations

import pytest
from apps.api.schemas import ScenarioDefinition, ScenarioPlanDefinition, ScenarioPlanPayload
from pydantic import ValidationError


def test_plan_definition_omits_unset_defaultable_fields() -> None:
    definition = ScenarioPlanDefinition(name="baseline")

    assert definition.to_mapping() == {"name": "baseline"}


def test_plan_definition_preserves_explicit_null_overrides() -> None:
    definition = ScenarioPlanDefinition(
        name="clear-scopes",
        commodity_symbols=None,
        jurisdictions=None,
    )

    assert definition.to_mapping() == {
        "name": "clear-scopes",
        "commodity_symbols": None,
        "jurisdictions": None,
    }


def test_batch_scenario_definition_still_requires_base_currency() -> None:
    with pytest.raises(ValidationError):
        ScenarioDefinition(name="strict-batch")


def test_plan_payload_applies_defaults_and_preserves_scenario_overrides() -> None:
    payload = ScenarioPlanPayload.model_validate(
        {
            "metadata": {"name": "Defaults Contract"},
            "defaults": {
                "base_currency": "USD",
                "commodity_symbols": ["XAU"],
                "jurisdictions": ["US"],
            },
            "scenarios": [
                {"name": "defaulted"},
                {
                    "name": "overridden",
                    "base_currency": "EUR",
                    "commodity_symbols": [],
                    "jurisdictions": None,
                },
            ],
        }
    )

    assert payload.scenarios[0].to_mapping() == {"name": "defaulted"}
    assert payload.scenarios[1].to_mapping()["jurisdictions"] is None

    plan = payload.to_plan()

    assert plan.scenarios[0].base_currency == "USD"
    assert plan.scenarios[0].commodity_symbols == ("XAU",)
    assert plan.scenarios[0].jurisdictions == ("US",)
    assert plan.scenarios[1].base_currency == "EUR"
    assert plan.scenarios[1].commodity_symbols == ()
    assert plan.scenarios[1].jurisdictions is None
