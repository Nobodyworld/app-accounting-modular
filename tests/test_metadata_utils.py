"""Metadata utility tests covering normalisation and serialisation helpers."""

from datetime import date, datetime, timezone
from decimal import Decimal

from apps.api.utils.metadata import (
    merge_forecast_diagnostics,
    normalise_metadata,
    prepare_metadata_for_response,
    serialise_diagnostics,
)


def test_normalise_metadata_handles_nested_structures() -> None:
    raw = {
        "GeneratedAt": datetime(2024, 1, 1, 12, 0).isoformat(),
        "ForecastDiagnostics": {"AIC": 123.4, "Observations": 10},
        "Tags": [
            {"KeyName": "Environment", "KeyValue": "Prod"},
            "plain",  # passthrough
        ],
    }

    normalised = normalise_metadata(raw)

    assert set(normalised.keys()) == {"generated_at", "forecast_diagnostics", "tags"}
    assert isinstance(normalised["generated_at"], datetime)
    assert normalised["forecast_diagnostics"]["observations"] == 10
    assert normalised["tags"][0]["key_name"] == "Environment"


def test_normalise_metadata_parses_zulu_timestamps() -> None:
    normalised = normalise_metadata({"generated_at": "2024-01-01T12:00:00Z"})

    value = normalised["generated_at"]
    assert isinstance(value, datetime)
    assert value.tzinfo == timezone.utc


def test_normalise_metadata_preserves_non_iso_strings() -> None:
    normalised = normalise_metadata({"generated_at": "not-a-timestamp"})

    assert normalised["generated_at"] == "not-a-timestamp"


def test_serialise_diagnostics_coerces_scalars() -> None:
    diagnostics = {
        "observations": 12,
        "baseline": Decimal("42.125"),
        "generated": datetime(2024, 2, 1, 12, 0, tzinfo=timezone.utc),
        "effective_date": date(2024, 2, 1),
        "active": True,
        "notes": None,
    }

    serialised = serialise_diagnostics(diagnostics)

    assert serialised == {
        "observations": 12,
        "baseline": 42.125,
        "generated": "2024-02-01T12:00:00+00:00",
        "effective_date": "2024-02-01",
        "active": True,
    }


def test_serialise_diagnostics_stringifies_unknown_types() -> None:
    class Custom:
        def __str__(self) -> str:
            return "custom-value"

    serialised = serialise_diagnostics({"object": Custom()})

    assert serialised["object"] == "custom-value"


def test_serialise_diagnostics_handles_non_finite_floats() -> None:
    serialised = serialise_diagnostics({"nan": float("nan"), "inf": float("inf")})

    assert serialised == {"nan": "nan", "inf": "inf"}


def test_merge_forecast_diagnostics_preserves_existing_values() -> None:
    metadata: dict[str, object] = {
        "forecast_diagnostics": {
            "observations": 3,
            "baseline": 2.0,
        }
    }

    merge_forecast_diagnostics(metadata, {"drift": Decimal("1.25")})

    diagnostics = metadata["forecast_diagnostics"]
    assert diagnostics == {"observations": 3, "baseline": 2.0, "drift": 1.25}


def test_merge_forecast_diagnostics_serialises_new_payload() -> None:
    metadata: dict[str, object] = {}

    merge_forecast_diagnostics(
        metadata,
        {
            "generated": datetime(2024, 4, 1, 0, 0),
            "label": "april",
        },
    )

    diagnostics = metadata["forecast_diagnostics"]
    assert diagnostics["generated"].startswith("2024-04-01T00:00:00")
    assert diagnostics["label"] == "april"


def test_prepare_metadata_for_response_combines_normalisation_steps() -> None:
    metadata = {
        "GeneratedAt": "2024-03-01T12:00:00",
        "forecastDiagnostics": {"observations": 5, "flag": True, "note": None},
    }

    prepared = prepare_metadata_for_response(metadata)

    assert prepared["generated_at"].tzinfo == timezone.utc
    assert prepared["forecast_diagnostics"] == {"observations": 5, "flag": True}


# TODO - (metadata) Test resilience when metadata contains deeply nested arrays.
