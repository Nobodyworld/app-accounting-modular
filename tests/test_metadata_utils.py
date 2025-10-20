from datetime import datetime, timezone

from apps.api.utils.metadata import normalise_metadata


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
