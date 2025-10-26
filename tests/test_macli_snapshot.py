import json
from datetime import UTC, datetime
from decimal import Decimal

from click.testing import CliRunner

from apps.modular_accounting.application import (
    DataSnapshot,
    SnapshotDiagnostics,
    SnapshotRequest,
    compute_snapshot_diagnostics,
)
from apps.modular_accounting.application.cache import CacheStats
from apps.modular_accounting.domain import CommodityQuote, FXRate, Money, TaxRule


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


def test_macli_snapshot_json(monkeypatch) -> None:
    from cli import macli as macli_module
    from apps.api.services.snapshot_service import SnapshotResult

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
    output = result.output
    marker = output.find('"fx_rates"')
    if marker == -1:  # pragma: no cover - defensive fallback
        raise AssertionError("Snapshot payload not found in CLI output")
    start = output.rfind("{", 0, marker)
    if start == -1:  # pragma: no cover - defensive fallback
        raise AssertionError("Snapshot payload not found in CLI output")
    depth = 0
    in_string = False
    escape = False
    end = None
    for index in range(start, len(output)):
        char = output[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
        else:
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
        raise AssertionError("Snapshot payload not terminated in CLI output")
    payload = json.loads(output[start:end])
    assert payload["providers"]["fx"] == "fx:stub"
    assert payload["request"]["base_currency"] == "USD"
    assert payload["diagnostics"]["tax_rule_count"] == 1


def test_macli_snapshot_table(monkeypatch) -> None:
    from cli import macli as macli_module
    from apps.api.services.snapshot_service import SnapshotResult

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
