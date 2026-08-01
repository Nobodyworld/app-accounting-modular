"""Deterministic schema and metadata boundary contracts for expensive inputs."""

from __future__ import annotations

from datetime import date

import pytest
from apps.api.limits import (
    MAX_JURISDICTIONS_PER_SCENARIO,
    MAX_METADATA_DEPTH,
    MAX_METADATA_KEYS_PER_MAPPING,
    MAX_METADATA_STRING_LENGTH,
    MAX_METADATA_TOTAL_NODES,
    MAX_MODELS_PER_BACKTEST,
    MAX_POSTINGS_PER_TRANSACTION,
    MAX_REGRESSOR_FIELDS,
    MAX_SCENARIOS_PER_BATCH,
    MAX_SERIES_POINTS,
    MAX_STAGED_IDS_PER_REQUEST,
    MAX_SYMBOLS_PER_SCENARIO,
    MAX_TAG_LENGTH,
    MAX_TAGS_PER_OBJECT,
    MAX_WORKFLOW_TRANSACTIONS,
)
from apps.api.schemas import (
    BacktestRequest,
    CausalImpactRequest,
    ForecastRequest,
    ScenarioBatchRequest,
    ScenarioPlanPayload,
    WorkflowIngestRequest,
    WorkflowProcessRequest,
)
from pydantic import ValidationError


def _max_length(model: type, field_name: str) -> int | None:
    for constraint in model.model_fields[field_name].metadata:
        value = getattr(constraint, "max_length", None)
        if value is not None:
            return int(value)
    return None


def _series(count: int) -> list[tuple[str, float]]:
    return [(f"2024-01-{index % 28 + 1:02d}", float(index)) for index in range(count)]


def _scenario(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {"name": "baseline", "base_currency": "USD"}
    value.update(overrides)
    return value


def _transaction(*, postings: int = 1) -> dict[str, object]:
    return {
        "date": date(2024, 1, 1),
        "description": "bounded transaction",
        "postings": [{"account_code": "1000", "debit": "1", "credit": "0"}] * postings,
    }


def _nested_metadata(depth: int) -> dict[str, object]:
    value: object = "leaf"
    for _ in range(depth):
        value = {"child": value}
    assert isinstance(value, dict)
    return value


@pytest.mark.parametrize(
    ("model", "field_name"),
    [
        (ForecastRequest, "series"),
        (ScenarioBatchRequest, "scenarios"),
        (WorkflowIngestRequest, "transactions"),
    ],
)
def test_audit_collection_fields_publish_bounded_max_length(model: type, field_name: str) -> None:
    maximum = _max_length(model, field_name)
    assert maximum is not None
    assert 0 < maximum <= 10_000


def test_forecast_series_accepts_normal_and_exact_limit() -> None:
    assert len(ForecastRequest(series=[("2024-01-01", 1.0)], organization_id=1).series) == 1
    assert len(ForecastRequest(series=_series(MAX_SERIES_POINTS), organization_id=1).series) == MAX_SERIES_POINTS


def test_forecast_series_rejects_limit_plus_one() -> None:
    with pytest.raises(ValidationError):
        ForecastRequest(series=_series(MAX_SERIES_POINTS + 1), organization_id=1)


def test_forecast_regressors_bound_field_count_and_each_nested_series() -> None:
    at_field_limit = {f"r{index}": [("2024-01-01", 1.0)] for index in range(MAX_REGRESSOR_FIELDS)}
    assert len(ForecastRequest(regressors=at_field_limit, organization_id=1).regressors or {}) == MAX_REGRESSOR_FIELDS
    exact_series = ForecastRequest(
        regressors={"driver": _series(MAX_SERIES_POINTS)},
        organization_id=1,
    )
    assert len((exact_series.regressors or {})["driver"]) == MAX_SERIES_POINTS
    with pytest.raises(ValidationError):
        ForecastRequest(
            regressors={f"r{index}": [] for index in range(MAX_REGRESSOR_FIELDS + 1)},
            organization_id=1,
        )
    with pytest.raises(ValidationError):
        ForecastRequest(regressors={"driver": _series(MAX_SERIES_POINTS + 1)}, organization_id=1)


def test_forecast_horizon_and_model_are_bounded() -> None:
    assert ForecastRequest(horizon=365, model="m", organization_id=1).horizon == 365
    with pytest.raises(ValidationError):
        ForecastRequest(horizon=366, organization_id=1)
    with pytest.raises(ValidationError):
        ForecastRequest(model="m" * 129, organization_id=1)


def test_backtest_models_series_regressors_and_controls_are_bounded() -> None:
    request = BacktestRequest(
        series=_series(MAX_SERIES_POINTS),
        models=[f"m{index}" for index in range(MAX_MODELS_PER_BACKTEST)],
        regressors={"driver": _series(MAX_SERIES_POINTS)},
        horizon=365,
        initial_window=MAX_SERIES_POINTS,
        step=MAX_SERIES_POINTS,
        organization_id=1,
    )
    assert len(request.series) == MAX_SERIES_POINTS
    assert len(request.models or []) == MAX_MODELS_PER_BACKTEST
    with pytest.raises(ValidationError):
        BacktestRequest(series=_series(MAX_SERIES_POINTS + 1), organization_id=1)
    with pytest.raises(ValidationError):
        BacktestRequest(models=["m"] * (MAX_MODELS_PER_BACKTEST + 1), organization_id=1)
    with pytest.raises(ValidationError):
        BacktestRequest(regressors={"driver": _series(MAX_SERIES_POINTS + 1)}, organization_id=1)
    for field_name in ("horizon", "initial_window", "step"):
        with pytest.raises(ValidationError):
            BacktestRequest(**{field_name: MAX_SERIES_POINTS + 1, "organization_id": 1})


def test_causal_impact_interventions_series_and_model_are_bounded() -> None:
    request = CausalImpactRequest(
        series=_series(MAX_SERIES_POINTS),
        event_start="2024-01-01",
        interventions={"campaign": _series(MAX_SERIES_POINTS)},
        organization_id=1,
    )
    assert len(request.series) == MAX_SERIES_POINTS
    with pytest.raises(ValidationError):
        CausalImpactRequest(
            series=_series(MAX_SERIES_POINTS + 1),
            event_start="2024-01-01",
            organization_id=1,
        )
    with pytest.raises(ValidationError):
        CausalImpactRequest(
            event_start="2024-01-01",
            interventions={f"i{index}": [] for index in range(MAX_REGRESSOR_FIELDS + 1)},
            organization_id=1,
        )
    with pytest.raises(ValidationError):
        CausalImpactRequest(
            event_start="2024-01-01",
            interventions={"campaign": _series(MAX_SERIES_POINTS + 1)},
            organization_id=1,
        )


def test_direct_scenario_count_accepts_normal_and_exact_limit_then_rejects_plus_one() -> None:
    assert len(ScenarioBatchRequest(scenarios=[_scenario()]).scenarios) == 1
    assert (
        len(ScenarioBatchRequest(scenarios=[_scenario(name=f"s{index}") for index in range(100)]).scenarios)
        == MAX_SCENARIOS_PER_BATCH
    )
    with pytest.raises(ValidationError):
        ScenarioBatchRequest(scenarios=[_scenario(name=f"s{index}") for index in range(101)])


@pytest.mark.parametrize(
    ("field_name", "maximum"),
    [
        ("commodity_symbols", MAX_SYMBOLS_PER_SCENARIO),
        ("jurisdictions", MAX_JURISDICTIONS_PER_SCENARIO),
        ("tags", MAX_TAGS_PER_OBJECT),
    ],
)
def test_scenario_nested_collections_accept_exact_limit_and_reject_plus_one(field_name: str, maximum: int) -> None:
    values = [f"v{index}" for index in range(maximum)]
    assert (
        len(getattr(ScenarioBatchRequest(scenarios=[_scenario(**{field_name: values})]).scenarios[0], field_name))
        == maximum
    )
    with pytest.raises(ValidationError):
        ScenarioBatchRequest(scenarios=[_scenario(**{field_name: values + ["overflow"]})])


def test_scenario_tag_length_accepts_exact_limit_and_rejects_plus_one() -> None:
    assert (
        len(ScenarioBatchRequest(scenarios=[_scenario(tags=["t" * MAX_TAG_LENGTH])]).scenarios[0].tags[0])
        == MAX_TAG_LENGTH
    )
    with pytest.raises(ValidationError):
        ScenarioBatchRequest(scenarios=[_scenario(tags=["t" * (MAX_TAG_LENGTH + 1)])])


def test_plan_scenarios_defaults_and_parameters_are_bounded() -> None:
    normal = ScenarioPlanPayload.model_validate(
        {
            "metadata": {"name": "plan", "parameters": {"owner": "finance"}},
            "defaults": {"base_currency": "USD"},
            "scenarios": [{"name": "baseline"}],
        }
    )
    assert normal.defaults == {"base_currency": "USD"}
    exact = ScenarioPlanPayload.model_validate(
        {
            "metadata": {"name": "plan", "parameters": {"note": "x" * MAX_METADATA_STRING_LENGTH}},
            "defaults": {"note": "x" * MAX_METADATA_STRING_LENGTH},
            "scenarios": [{"name": f"s{index}"} for index in range(MAX_SCENARIOS_PER_BATCH)],
        }
    )
    assert len(exact.scenarios) == MAX_SCENARIOS_PER_BATCH
    with pytest.raises(ValidationError):
        ScenarioPlanPayload.model_validate(
            {
                "metadata": {"name": "plan", "parameters": _nested_metadata(MAX_METADATA_DEPTH + 1)},
                "scenarios": [{"name": "baseline"}],
            }
        )
    with pytest.raises(ValidationError):
        ScenarioPlanPayload.model_validate(
            {
                "metadata": {"name": "plan"},
                "defaults": {"note": "x" * (MAX_METADATA_STRING_LENGTH + 1)},
                "scenarios": [{"name": "baseline"}],
            }
        )


def test_workflow_transaction_and_posting_counts_are_bounded_before_processing() -> None:
    normal = WorkflowIngestRequest(transactions=[_transaction()])
    assert len(normal.transactions) == 1
    exact_transactions = WorkflowIngestRequest(transactions=[_transaction() for _ in range(MAX_WORKFLOW_TRANSACTIONS)])
    assert len(exact_transactions.transactions) == MAX_WORKFLOW_TRANSACTIONS
    with pytest.raises(ValidationError):
        WorkflowIngestRequest(transactions=[_transaction() for _ in range(MAX_WORKFLOW_TRANSACTIONS + 1)])
    exact_postings = WorkflowIngestRequest(transactions=[_transaction(postings=MAX_POSTINGS_PER_TRANSACTION)])
    assert len(exact_postings.transactions[0].postings) == MAX_POSTINGS_PER_TRANSACTION
    with pytest.raises(ValidationError):
        WorkflowIngestRequest(transactions=[_transaction(postings=MAX_POSTINGS_PER_TRANSACTION + 1)])


def test_staged_id_limit_applies_before_any_deduplication() -> None:
    assert (
        len(WorkflowProcessRequest(staged_ids=[1] * MAX_STAGED_IDS_PER_REQUEST).staged_ids or [])
        == MAX_STAGED_IDS_PER_REQUEST
    )
    with pytest.raises(ValidationError):
        WorkflowProcessRequest(staged_ids=[1] * (MAX_STAGED_IDS_PER_REQUEST + 1))


def test_metadata_depth_accepts_exact_limit_and_rejects_plus_one() -> None:
    assert WorkflowIngestRequest(metadata=_nested_metadata(MAX_METADATA_DEPTH), transactions=[_transaction()])
    with pytest.raises(ValidationError):
        WorkflowIngestRequest(metadata=_nested_metadata(MAX_METADATA_DEPTH + 1), transactions=[_transaction()])


def test_metadata_keys_accept_exact_limit_and_rejects_plus_one() -> None:
    exact = {f"k{index}": index for index in range(MAX_METADATA_KEYS_PER_MAPPING)}
    assert WorkflowIngestRequest(metadata=exact, transactions=[_transaction()]).metadata == exact
    with pytest.raises(ValidationError):
        WorkflowIngestRequest(
            metadata={**exact, "overflow": True},
            transactions=[_transaction()],
        )


def test_metadata_nodes_accept_exact_limit_and_rejects_plus_one() -> None:
    exact = {"items": [None] * (MAX_METADATA_TOTAL_NODES - 2)}
    assert WorkflowIngestRequest(metadata=exact, transactions=[_transaction()]).metadata == exact
    with pytest.raises(ValidationError):
        WorkflowIngestRequest(
            metadata={"items": [None] * (MAX_METADATA_TOTAL_NODES - 1)},
            transactions=[_transaction()],
        )


def test_metadata_string_length_accepts_exact_limit_and_rejects_plus_one() -> None:
    exact = {"note": "x" * MAX_METADATA_STRING_LENGTH}
    assert WorkflowIngestRequest(metadata=exact, transactions=[_transaction()]).metadata == exact
    with pytest.raises(ValidationError):
        WorkflowIngestRequest(
            metadata={"note": "x" * (MAX_METADATA_STRING_LENGTH + 1)},
            transactions=[_transaction()],
        )


@pytest.mark.parametrize(
    "metadata_path",
    [
        ("transactions", 0, "metadata"),
        ("transactions", 0, "postings", 0, "metadata"),
    ],
)
def test_nested_workflow_metadata_fields_use_shared_validation(metadata_path: tuple[object, ...]) -> None:
    payload = {"transactions": [_transaction()]}
    target: object = payload
    for part in metadata_path[:-1]:
        target = target[part]  # type: ignore[index]
    target[metadata_path[-1]] = {"note": "x" * (MAX_METADATA_STRING_LENGTH + 1)}  # type: ignore[index]
    with pytest.raises(ValidationError):
        WorkflowIngestRequest.model_validate(payload)


def test_metadata_rejects_non_json_objects_without_mutating_valid_values() -> None:
    metadata = {"nested": [1, True, None, {"text": "same"}]}
    request = WorkflowIngestRequest(metadata=metadata, transactions=[_transaction()])
    assert request.metadata == metadata
    with pytest.raises(ValidationError):
        WorkflowIngestRequest(metadata={"unsupported": object()}, transactions=[_transaction()])
