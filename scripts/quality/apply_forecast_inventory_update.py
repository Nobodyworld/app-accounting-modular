"""Update forecast route evidence before deterministic inventory regeneration."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET = REPO_ROOT / "scripts/security/inventory_routes.py"


def replace_exact(content: str, old: str, new: str) -> str:
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"expected one policy block, found {count}: {old[:80]!r}")
    return content.replace(old, new)


def main() -> None:
    content = TARGET.read_text(encoding="utf-8")
    replacements = {
        '''    "POST /forecast/series": Policy(
        "tenant member",
        "organization_id",
        "caller-supplied series (compute forecast)",
        "tests/test_forecast_service.py; tests/test_input_limits.py; tests/test_request_body_limits.py",
        "route-level no-membership",
    ),
''': '''    "POST /forecast/series": Policy(
        "tenant member",
        "organization_id",
        "caller-supplied finite regular-cadence series (compute forecast)",
        "tests/test_forecast_api.py::test_tenant_authorization_runs_before_forecast_work; "
        "tests/test_forecast_service.py; tests/test_forecast_robustness.py; tests/test_input_limits.py; "
        "tests/test_request_body_limits.py",
        "none identified",
    ),
''',
        '''    "GET /forecast/models": Policy(
        "tenant member",
        "organization_id",
        "forecast model catalog (read)",
        "tests/test_forecast_service.py",
        "route-level no-membership",
    ),
''': '''    "GET /forecast/models": Policy(
        "tenant member",
        "organization_id",
        "bounded forecast model catalog and optional-dependency status (read)",
        "tests/test_forecast_api.py::test_tenant_authorization_runs_before_forecast_work; "
        "tests/test_forecast_service.py",
        "none identified",
    ),
''',
        '''    "POST /forecast/backtest": Policy(
        "tenant member",
        "organization_id",
        "caller-supplied series (compute backtests)",
        "tests/test_forecast_service.py; tests/test_input_limits.py; tests/test_request_body_limits.py",
        "route-level no-membership",
    ),
''': '''    "POST /forecast/backtest": Policy(
        "tenant member",
        "organization_id",
        "caller-supplied finite regular-cadence series (compute bounded backtests)",
        "tests/test_forecast_api.py::test_tenant_authorization_runs_before_forecast_work; "
        "tests/test_forecast_service.py; tests/test_forecast_robustness.py; tests/test_input_limits.py; "
        "tests/test_request_body_limits.py",
        "none identified",
    ),
''',
        '''    "POST /forecast/impact": Policy(
        "tenant member",
        "organization_id",
        "caller-supplied series (compute causal impact)",
        "tests/test_forecast_service.py; tests/test_input_limits.py; tests/test_request_body_limits.py",
        "route-level no-membership",
    ),
''': '''    "POST /forecast/impact": Policy(
        "tenant member",
        "organization_id",
        "caller-supplied finite regular-cadence series and contained event window (compute causal impact)",
        "tests/test_forecast_api.py::test_tenant_authorization_runs_before_forecast_work; "
        "tests/test_forecast_service.py; tests/test_forecast_robustness.py; tests/test_input_limits.py; "
        "tests/test_request_body_limits.py",
        "none identified",
    ),
''',
    }
    for old, new in replacements.items():
        content = replace_exact(content, old, new)
    TARGET.write_text(content, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
