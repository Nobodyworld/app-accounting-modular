"""Tests for snapshot diagnostics helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from apps.modular_accounting.application import (
    DataSnapshot,
    SnapshotRequest,
    compute_snapshot_diagnostics,
)
from apps.modular_accounting.domain import CommodityQuote, FXRate, Money, TaxRule


def _snapshot_fixture() -> tuple[SnapshotRequest, DataSnapshot]:
    request = SnapshotRequest(
        base_currency="USD",
        commodity_symbols=("XAU",),
        jurisdictions=("US", "CA"),
    )
    snapshot = DataSnapshot(
        fx_rates=(
            FXRate(
                base_currency="USD",
                quote_currency="EUR",
                rate=Decimal("0.92"),
                as_of=datetime(2024, 1, 1, tzinfo=UTC),
            ),
            FXRate(
                base_currency="USD",
                quote_currency="GBP",
                rate=Decimal("0.78"),
                as_of=datetime(2024, 1, 1, tzinfo=UTC) - timedelta(hours=12),
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
                effective_from=date(2023, 1, 1),
            ),
            TaxRule(
                jurisdiction="CA",
                rate=Decimal("0.085"),
                description="GST",
                effective_from=date(2022, 6, 1),
                effective_to=date(2025, 1, 1),
            ),
        ),
    )
    return request, snapshot


def test_compute_snapshot_diagnostics_counts_and_age() -> None:
    request, snapshot = _snapshot_fixture()
    now = datetime(2024, 1, 2, tzinfo=UTC)
    diagnostics = compute_snapshot_diagnostics(
        snapshot,
        request=request,
        now=lambda: now,
        today=lambda: now.date(),
    )

    assert diagnostics.base_currency == "USD"
    assert diagnostics.fx_pairs == ("USD/EUR", "USD/GBP")
    assert diagnostics.fx_rate_count == 2
    assert diagnostics.fx_max_age_seconds is not None
    assert diagnostics.fx_max_age_seconds >= 43200
    assert diagnostics.commodity_symbols == ("XAU",)
    assert diagnostics.commodity_quote_count == 1
    assert diagnostics.tax_jurisdictions == ("US", "CA")
    assert diagnostics.active_tax_rule_count == 2
    assert diagnostics.missing_sections == ()


def test_compute_snapshot_diagnostics_handles_missing_sections() -> None:
    snapshot = DataSnapshot(fx_rates=(), commodity_quotes=(), tax_rules=())
    diagnostics = compute_snapshot_diagnostics(
        snapshot,
        request=None,
        now=lambda: datetime(2024, 1, 1, tzinfo=UTC),
        today=lambda: date(2024, 1, 1),
    )

    assert diagnostics.base_currency is None
    assert diagnostics.missing_sections == ("fx", "commodities", "tax")
    assert diagnostics.fx_max_age_seconds is None
    assert diagnostics.commodity_symbols == ()
