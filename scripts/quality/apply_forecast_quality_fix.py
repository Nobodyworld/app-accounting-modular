"""Apply exact forecast quality corrections for the temporary branch workflow."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def replace_exact(path: str, old: str, new: str, *, expected: int = 1) -> None:
    target = REPO_ROOT / path
    content = target.read_text(encoding="utf-8")
    count = content.count(old)
    if count != expected:
        raise RuntimeError(f"{path}: expected {expected} occurrences, found {count}: {old!r}")
    target.write_text(content.replace(old, new), encoding="utf-8", newline="\n")


def main() -> None:
    service = "src/apps/api/services/forecast_service.py"
    replace_exact(service, "from typing import Any\n", "from typing import Any, cast\n")
    replace_exact(
        service,
        "from pandas import DatetimeIndex\n",
        "from pandas import DatetimeIndex\n"
        "from pandas.tseries.offsets import BaseOffset\n"
        "from statsmodels.tsa.arima.model import ARIMA\n",
    )
    replace_exact(service, "\nARIMA = _legacy.ARIMA\n", "\n")
    replace_exact(service, "result = float(value)", "result = float(cast(Any, value))")
    replace_exact(service, "result = pd.Timestamp(value)", "result = pd.Timestamp(cast(Any, value))")
    replace_exact(
        service,
        "def _cadence_label(offset: pd.DateOffset, *, prefix: str | None = None) -> str:",
        "def _cadence_label(offset: BaseOffset, *, prefix: str | None = None) -> str:",
    )
    replace_exact(
        service,
        "def _infer_cadence(cls, index: DatetimeIndex) -> tuple[pd.DateOffset, str]:",
        "def _infer_cadence(cls, index: DatetimeIndex) -> tuple[BaseOffset, str]:",
    )
    replace_exact(
        service,
        "            offset = pd.offsets.Day(1)\n",
        "            offset: BaseOffset = pd.offsets.Day(1)\n",
    )
    replace_exact(
        service,
        '        timezone = "UTC" if timezone_key in (None, "naive") else timezone_key\n',
        '        timezone = "UTC"\n'
        '        if timezone_key is not None and timezone_key != "naive":\n'
        "            timezone = timezone_key\n",
    )
    replace_exact(
        service,
        '        _legacy.ARIMA = ARIMA\n',
        '        cast(Any, _legacy).ARIMA = ARIMA\n',
    )
    replace_exact(
        service,
        "            for name, value in result.metrics.items():\n"
        "                if value is not None:\n"
        "                    self._finite_float(value, f\"Backtest metric '{name}'\")\n",
        "            for name, metric_value in result.metrics.items():\n"
        "                if metric_value is not None:\n"
        "                    self._finite_float(metric_value, f\"Backtest metric '{name}'\")\n",
    )

    router = "src/apps/api/routers/forecast.py"
    replace_exact(router, "from typing import TypeVar\n\n", "\n")
    replace_exact(router, '\n_ResultT = TypeVar("_ResultT")\n', "\n")
    replace_exact(
        router,
        "def _execute_forecast(operation: str, action: Callable[[], _ResultT]) -> _ResultT:",
        "def _execute_forecast[ResultT](operation: str, action: Callable[[], ResultT]) -> ResultT:",
    )


if __name__ == "__main__":
    main()
