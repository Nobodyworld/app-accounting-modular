import json
from datetime import UTC, datetime
from decimal import Decimal

from apps.modular_accounting.application import (
    DataSnapshot,
    ScenarioBatchResult,
    ScenarioResult,
    ScenarioSummary,
    SnapshotDiagnostics,
    SnapshotRequest,
    SnapshotScenario,
    compute_snapshot_diagnostics,
)
from apps.modular_accounting.application.cache import CacheStats
from apps.modular_accounting.domain import CommodityQuote, FXRate, Money, TaxRule
from click.testing import CliRunner


def _extract_json_payload(output: str, *, required_key: str | None = None) -> dict[str, object]:
    cursor = 0
    while True:
        marker = output.find("{", cursor)
        if marker == -1:  # pragma: no cover - defensive fallback
            raise AssertionError("JSON payload not found in CLI output")
        depth = 0
        in_string = False
        escape = False
        end = None
        for index in range(marker, len(output)):
            char = output[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end is None:  # pragma: no cover - defensive fallback
            raise AssertionError("JSON payload not terminated in CLI output")
        chunk = json.loads(output[marker:end])
        if required_key is None or required_key in chunk:
            return chunk
        cursor = end


def _stub_result() -> tuple[
    SnapshotRequest,
    DataSnapshot,
    SnapshotDiagnostics,
    dict[str, CacheStats],
    dict[str, str],
]:
    request = SnapshotRequest(
        base_currency="USD",
        commodity_symbols=("XAU",),
        jurisdictions=("US",),
    )
    snapshot = DataSnapshot(
        fx_rates=(
            FXRate(
                base_currency="USD",
                quote_currency="EUR",
                rate=Decimal("0.92"),
                as_of=datetime(2024, 1, 1, tzinfo=UTC),
            ),
        ),
        commodity_quotes=(
            CommodityQuote(
                symbol="XAU",
                price=Money(amount=Decimal("1950.10"), currency="USD"),
                as_of=datetime(2024, 1, 1, tzinfo=UTC),
            ),
        ),
        tax_rules=(
            TaxRule(
                jurisdiction="US",
                rate=Decimal("0.070"),
                description="Sales tax",
                effective_from=datetime(2023, 1, 1, tzinfo=UTC).date(),
            ),
        ),
    )
    diagnostics = compute_snapshot_diagnostics(
        snapshot,
        request=request,
        now=lambda: datetime(2024, 1, 2, tzinfo=UTC),
        today=lambda: datetime(2024, 1, 2, tzinfo=UTC).date(),
    )
    cache_stats = {
        "fx": CacheStats(size=1, hits=1, misses=0),
        "commodities": CacheStats(size=1, hits=0, misses=0),
        "tax": CacheStats(size=1, hits=0, misses=0),
    }
    providers = {
        "fx": "fx:stub",
        "commodity": "market:stub",
        "tax": "tax:stub",
    }
    return request, snapshot, diagnostics, cache_stats, providers


def _stub_batch() -> ScenarioBatchResult:
    request, snapshot, diagnostics, cache_stats, providers = _stub_result()
    scenario = SnapshotScenario(name="demo", request=request, tags=("test",))
    result = ScenarioResult(
        scenario=scenario,
        snapshot=snapshot,
        diagnostics=diagnostics,
        cache_stats=cache_stats,
        providers=providers,
    )
    summary = ScenarioSummary(
        scenario_count=1,
        base_currencies=(request.base_currency,),
        commodity_symbols=request.commodity_symbols,
        jurisdictions=request.jurisdictions or (),
        missing_sections={},
        total_fx_rates=diagnostics.fx_rate_count,
        total_commodity_quotes=diagnostics.commodity_quote_count,
        total_tax_rules=diagnostics.tax_rule_count,
        max_fx_age_seconds=diagnostics.fx_max_age_seconds,
        max_commodity_age_seconds=diagnostics.commodity_max_age_seconds,
        max_active_tax_rules=diagnostics.active_tax_rule_count,
    )
    return ScenarioBatchResult(results=(result,), summary=summary)


def test_macli_snapshot_json(monkeypatch) -> None:
    from apps.api.services.snapshot_service import SnapshotResult
    from cli import macli as macli_module

    request, snapshot, diagnostics, cache_stats, providers = _stub_result()
    snapshot_result = SnapshotResult(
        request=request,
        snapshot=snapshot,
        diagnostics=diagnostics,
        providers=providers,
        cache_stats=cache_stats,
    )

    class DummyOrchestrator:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def build_snapshot(self, **kwargs):
            self.called_with = kwargs
            return snapshot_result

    monkeypatch.setattr(macli_module, "SnapshotOrchestrator", DummyOrchestrator)

    runner = CliRunner()
    result = runner.invoke(macli_module.cli, ["snapshot", "--format", "json"])
    assert result.exit_code == 0
    payload = _extract_json_payload(result.output)
    assert payload["providers"]["fx"] == "fx:stub"
    assert payload["request"]["base_currency"] == "USD"
    assert payload["diagnostics"]["tax_rule_count"] == 1


def test_macli_snapshot_table(monkeypatch) -> None:
    from apps.api.services.snapshot_service import SnapshotResult
    from cli import macli as macli_module

    request, snapshot, diagnostics, cache_stats, providers = _stub_result()
    snapshot_result = SnapshotResult(
        request=request,
        snapshot=snapshot,
        diagnostics=diagnostics,
        providers=providers,
        cache_stats=cache_stats,
    )

    class DummyOrchestrator:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def build_snapshot(self, **kwargs):
            self.called_with = kwargs
            return snapshot_result

    monkeypatch.setattr(macli_module, "SnapshotOrchestrator", DummyOrchestrator)

    runner = CliRunner()
    result = runner.invoke(macli_module.cli, ["snapshot", "--format", "table"])
    assert result.exit_code == 0
    assert "Providers:" in result.output
    assert "XAU" in result.output
    assert "Diagnostics" in result.output


def test_macli_snapshot_scenarios_json(tmp_path, monkeypatch) -> None:
    from cli import macli as macli_module

    batch = _stub_batch()

    class DummyOrchestrator:
        def __init__(self, **kwargs):
            DummyOrchestrator.instance = self

        def run_scenarios(self, scenarios, reset_cache_between_runs: bool = False):
            self.called_with = list(scenarios)
            self.reset_cache = reset_cache_between_runs
            return batch

    monkeypatch.setattr(macli_module, "SnapshotOrchestrator", DummyOrchestrator)

    plan_path = tmp_path / "scenarios.json"
    plan_path.write_text(
        json.dumps(
            {
                "scenarios": [
                    {
                        "name": "demo",
                        "base_currency": "USD",
                        "commodity_symbols": ["XAU"],
                        "jurisdictions": ["US"],
                    }
                ]
            }
        )
    )

    runner = CliRunner()
    result = runner.invoke(
        macli_module.cli,
        [
            "snapshot-scenarios",
            "--plan",
            str(plan_path),
            "--format",
            "json",
            "--reset-cache",
        ],
    )

    assert result.exit_code == 0
    payload = _extract_json_payload(result.output, required_key="summary")
    assert payload["summary"]["scenario_count"] == 1
    assert payload["results"][0]["name"] == "demo"
    orchestrator = DummyOrchestrator.instance
    assert orchestrator.reset_cache is True
    assert orchestrator.called_with[0].name == "demo"


def test_macli_snapshot_scenarios_table(tmp_path, monkeypatch) -> None:
    from cli import macli as macli_module

    batch = _stub_batch()

    class DummyOrchestrator:
        def __init__(self, **kwargs):
            pass

        def run_scenarios(self, scenarios, reset_cache_between_runs: bool = False):
            return batch

    monkeypatch.setattr(macli_module, "SnapshotOrchestrator", DummyOrchestrator)

    plan_path = tmp_path / "scenarios.toml"
    plan_path.write_text(
        """
scenarios = [
  { name = "demo", base_currency = "USD", commodity_symbols = ["XAU"], jurisdictions = ["US"] }
]
""".strip()
    )

    runner = CliRunner()
    result = runner.invoke(
        macli_module.cli,
        ["snapshot-scenarios", "--plan", str(plan_path), "--format", "table"],
    )

    assert result.exit_code == 0
    assert "Scenario Summary" in result.output
    assert "demo" in result.output
