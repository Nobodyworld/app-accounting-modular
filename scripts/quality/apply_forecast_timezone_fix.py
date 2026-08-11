"""Apply the final forecast event-timezone correction and focused regression."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def replace_exact(path: str, old: str, new: str) -> None:
    target = REPO_ROOT / path
    content = target.read_text(encoding="utf-8")
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one occurrence, found {count}")
    target.write_text(content.replace(old, new), encoding="utf-8", newline="\n")


def main() -> None:
    replace_exact(
        "src/apps/api/services/forecast_service.py",
        '''        if timezone != target_timezone:
            if {timezone, target_timezone} == {"naive", "UTC"}:
                return timestamp
            raise ValueError(f"{label} must use the target series timezone")
''',
        '''        if timezone != target_timezone:
            raise ValueError(f"{label} must use the target series timezone")
''',
    )

    test_path = REPO_ROOT / "tests/test_forecast_robustness.py"
    content = test_path.read_text(encoding="utf-8")
    marker = '''def test_causal_event_window_must_be_ordered_and_contained() -> None:
'''
    if content.count(marker) != 1:
        raise RuntimeError("forecast robustness insertion point is not unique")
    addition = '''def test_causal_event_window_rejects_naive_date_for_aware_utc_series() -> None:
    service = ForecastService(minimum_observations=3)
    index = pd.date_range("2024-01-01", periods=10, freq="D", tz="UTC")
    series = [(timestamp, float(position)) for position, timestamp in enumerate(index)]

    with pytest.raises(ValueError, match="event_start must use the target series timezone"):
        service.causal_impact(series, event_start="2024-01-08")


'''
    test_path.write_text(content.replace(marker, addition + marker), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
