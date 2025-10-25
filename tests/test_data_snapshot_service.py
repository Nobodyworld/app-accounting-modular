"""Tests for DataSnapshotService with legacy and new keyword argument names."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

import pytest

from apps.modular_accounting.adapters import (
    InMemoryCommodityAdapter,
    InMemoryFXAdapter,
    InMemoryTaxAdapter,
)
from apps.modular_accounting.domain import TaxRule
from apps.modular_accounting.services import (
    DataSnapshotService,
    SnapshotRequest,
)


class RecordingCommodityAdapter(InMemoryCommodityAdapter):
    """Test double that records requested symbols for assertions."""

    def __init__(self, quotes: dict[str, Decimal]) -> None:
        super().__init__(quotes)
        self.seen: list[Sequence[str]] = []

    def get_quotes(self, symbols: Sequence[str]):  # type: ignore[override]
        self.seen.append(tuple(symbols))
        return super().get_quotes(symbols)


class CountingFXAdapter(InMemoryFXAdapter):
    """FX adapter that records how many times rates are requested."""

    def __init__(self, rates: dict[str, Decimal]) -> None:
        super().__init__(rates)
        self.calls = 0

    def get_rates(self, base_currency: str):  # type: ignore[override]
        self.calls += 1
        return super().get_rates(base_currency)


class CountingTaxAdapter(InMemoryTaxAdapter):
    """Tax adapter that records requested jurisdictions."""

    def __init__(self, rules: Sequence[TaxRule]) -> None:
        super().__init__(rules)
        self.requested: list[str | None] = []

    def get_rules(self, jurisdiction: str | None = None):  # type: ignore[override]
        self.requested.append(jurisdiction)
        return super().get_rules(jurisdiction)


class MutableClock:
    """Deterministic monotonic clock used for cache expiry tests."""

    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


@pytest.fixture
def fx_adapter():
    """Fixture providing a simple FX adapter."""
    return InMemoryFXAdapter({"EUR": Decimal("0.93"), "GBP": Decimal("0.79")})


@pytest.fixture
def commodity_adapter():
    """Fixture providing a simple commodity adapter."""
    return InMemoryCommodityAdapter(
        {"XAU": Decimal("2034.23"), "XAG": Decimal("24.83")}
    )


@pytest.fixture
def tax_adapter():
    """Fixture providing a simple tax adapter."""
    rules = [
        TaxRule(
            jurisdiction="us-ca",
            rate=Decimal("0.0825"),
            description="California sales tax",
            effective_from=date(2024, 1, 1),
        ),
        TaxRule(
            jurisdiction="uk",
            rate=Decimal("0.2000"),
            description="UK VAT",
            effective_from=date(2024, 1, 1),
        ),
    ]
    return InMemoryTaxAdapter(rules)


def test_init_with_positional_args(fx_adapter, commodity_adapter, tax_adapter):
    """Test DataSnapshotService can be initialized with positional arguments."""
    service = DataSnapshotService(fx_adapter, commodity_adapter, tax_adapter)
    assert service is not None


def test_init_with_legacy_keyword_args(fx_adapter, commodity_adapter, tax_adapter):
    """Test DataSnapshotService accepts legacy keyword argument names."""
    with pytest.warns(DeprecationWarning):
        service = DataSnapshotService(
            fx_adapter=fx_adapter,
            commodity_adapter=commodity_adapter,
            tax_adapter=tax_adapter,
        )
    assert service is not None


def test_init_with_new_keyword_args(fx_adapter, commodity_adapter, tax_adapter):
    """Test DataSnapshotService accepts new 'port' keyword argument names."""
    service = DataSnapshotService(
        fx_port=fx_adapter,
        commodity_port=commodity_adapter,
        tax_port=tax_adapter,
    )
    assert service is not None


def test_init_with_mixed_args(fx_adapter, commodity_adapter, tax_adapter):
    """Test DataSnapshotService accepts mixed legacy and new keyword names."""
    # New port names take precedence
    with pytest.warns(DeprecationWarning):
        service = DataSnapshotService(
            fx_adapter=fx_adapter,
            commodity_port=commodity_adapter,
            tax_adapter=tax_adapter,
        )
    assert service is not None


def test_init_raises_without_fx(commodity_adapter, tax_adapter):
    """Test DataSnapshotService raises TypeError when FX adapter is missing."""
    with pytest.warns(DeprecationWarning):
        with pytest.raises(TypeError, match="fx_adapter or fx_port"):
            DataSnapshotService(
                commodity_adapter=commodity_adapter,
                tax_adapter=tax_adapter,
            )


def test_init_raises_without_commodity(fx_adapter, tax_adapter):
    """Test DataSnapshotService raises TypeError when commodity adapter is missing."""
    with pytest.warns(DeprecationWarning):
        with pytest.raises(TypeError, match="commodity_adapter or commodity_port"):
            DataSnapshotService(
                fx_adapter=fx_adapter,
                tax_adapter=tax_adapter,
            )


def test_init_raises_without_tax(fx_adapter, commodity_adapter):
    """Test DataSnapshotService raises TypeError when tax adapter is missing."""
    with pytest.warns(DeprecationWarning):
        with pytest.raises(TypeError, match="tax_adapter or tax_port"):
            DataSnapshotService(
                fx_adapter=fx_adapter,
                commodity_adapter=commodity_adapter,
            )


def test_build_snapshot_with_legacy_args(fx_adapter, commodity_adapter, tax_adapter):
    """Test build_snapshot works correctly with legacy keyword args."""
    with pytest.warns(DeprecationWarning):
        service = DataSnapshotService(
            fx_adapter=fx_adapter,
            commodity_adapter=commodity_adapter,
            tax_adapter=tax_adapter,
        )
    
    snapshot = service.build_snapshot(
        base_currency="USD",
        commodity_symbols=["XAU", "XAG"],
        jurisdictions=["us-ca"],
    )
    
    assert len(snapshot.fx_rates) == 2
    assert len(snapshot.commodity_quotes) == 2
    assert len(snapshot.tax_rules) == 1
    assert snapshot.tax_rules[0].jurisdiction == "us-ca"


def test_build_snapshot_with_new_args(fx_adapter, commodity_adapter, tax_adapter):
    """Test build_snapshot works correctly with new 'port' keyword args."""
    service = DataSnapshotService(
        fx_port=fx_adapter,
        commodity_port=commodity_adapter,
        tax_port=tax_adapter,
    )
    
    snapshot = service.build_snapshot(
        base_currency="USD",
        commodity_symbols=["XAU"],
        jurisdictions=["uk"],
    )
    
    assert len(snapshot.fx_rates) == 2
    assert len(snapshot.commodity_quotes) == 1
    assert len(snapshot.tax_rules) == 1
    assert snapshot.tax_rules[0].jurisdiction == "uk"


def test_clear_cache_forces_refresh():
    fx_adapter = CountingFXAdapter({"EUR": Decimal("0.93")})
    commodity_adapter = RecordingCommodityAdapter({"XAU": Decimal("2034.23")})
    tax_rule = TaxRule(
        jurisdiction="us-ca",
        rate=Decimal("0.0825"),
        description="California sales tax",
        effective_from=date(2024, 1, 1),
    )
    tax_adapter = CountingTaxAdapter([tax_rule])

    service = DataSnapshotService(
        fx_port=fx_adapter,
        commodity_port=commodity_adapter,
        tax_port=tax_adapter,
    )

    request = SnapshotRequest(
        base_currency="USD",
        commodity_symbols=("XAU",),
        jurisdictions=("us-ca",),
    )

    service.create_snapshot(request)
    service.create_snapshot(request)
    assert fx_adapter.calls == 1
    assert commodity_adapter.seen == [("XAU",)]
    assert tax_adapter.requested == ["us-ca"]

    service.clear_cache()

    service.create_snapshot(request)
    assert fx_adapter.calls == 2
    assert commodity_adapter.seen == [("XAU",), ("XAU",)]
    assert tax_adapter.requested == ["us-ca", "us-ca"]


def test_cache_expiration_respects_ttl():
    clock = MutableClock()
    fx_adapter = CountingFXAdapter({"EUR": Decimal("0.93")})
    commodity_adapter = RecordingCommodityAdapter({"XAU": Decimal("2034.23")})
    tax_rule = TaxRule(
        jurisdiction="us-ca",
        rate=Decimal("0.0825"),
        description="California sales tax",
        effective_from=date(2024, 1, 1),
    )
    tax_adapter = CountingTaxAdapter([tax_rule])

    service = DataSnapshotService(
        fx_port=fx_adapter,
        commodity_port=commodity_adapter,
        tax_port=tax_adapter,
        default_cache_ttl=10,
        clock=clock,
    )

    request = SnapshotRequest(
        base_currency="USD",
        commodity_symbols=("XAU",),
        jurisdictions=("us-ca",),
    )

    service.create_snapshot(request)
    assert fx_adapter.calls == 1
    assert commodity_adapter.seen == [("XAU",)]
    assert tax_adapter.requested == ["us-ca"]

    clock.advance(5)
    service.create_snapshot(request)
    assert fx_adapter.calls == 1
    assert commodity_adapter.seen == [("XAU",)]
    assert tax_adapter.requested == ["us-ca"]

    clock.advance(6)
    service.create_snapshot(request)
    assert fx_adapter.calls == 2
    assert commodity_adapter.seen == [("XAU",), ("XAU",)]
    assert tax_adapter.requested == ["us-ca", "us-ca"]


def test_disable_caching_calls_ports_each_time():
    fx_adapter = CountingFXAdapter({"EUR": Decimal("0.93")})
    commodity_adapter = RecordingCommodityAdapter({"XAU": Decimal("2034.23")})
    tax_rule = TaxRule(
        jurisdiction="us-ca",
        rate=Decimal("0.0825"),
        description="California sales tax",
        effective_from=date(2024, 1, 1),
    )
    tax_adapter = CountingTaxAdapter([tax_rule])

    service = DataSnapshotService(
        fx_port=fx_adapter,
        commodity_port=commodity_adapter,
        tax_port=tax_adapter,
        enable_caching=False,
    )

    request = SnapshotRequest(
        base_currency="USD",
        commodity_symbols=("XAU",),
        jurisdictions=("us-ca",),
    )

    service.create_snapshot(request)
    service.create_snapshot(request)

    assert fx_adapter.calls == 2
    assert commodity_adapter.seen == [("XAU",), ("XAU",)]
    assert tax_adapter.requested == ["us-ca", "us-ca"]


def test_invalid_ttl_configuration_raises(fx_adapter, commodity_adapter, tax_adapter):
    with pytest.raises(ValueError):
        DataSnapshotService(
            fx_port=fx_adapter,
            commodity_port=commodity_adapter,
            tax_port=tax_adapter,
            default_cache_ttl=0,
        )


def test_cache_stats_report_hits_and_misses():
    fx_adapter = CountingFXAdapter({"EUR": Decimal("0.93")})
    commodity_adapter = RecordingCommodityAdapter({"XAU": Decimal("2034.23")})
    tax_rule = TaxRule(
        jurisdiction="us-ca",
        rate=Decimal("0.0825"),
        description="California sales tax",
        effective_from=date(2024, 1, 1),
    )
    tax_adapter = CountingTaxAdapter([tax_rule])

    service = DataSnapshotService(
        fx_port=fx_adapter,
        commodity_port=commodity_adapter,
        tax_port=tax_adapter,
    )

    stats = service.cache_stats()
    assert stats["fx"].size == 0
    assert stats["fx"].hits == 0
    assert stats["fx"].misses == 0

    request = SnapshotRequest(
        base_currency="USD",
        commodity_symbols=("XAU",),
        jurisdictions=("us-ca",),
    )

    service.create_snapshot(request)
    stats = service.cache_stats()
    assert stats["fx"].size == 1
    assert stats["fx"].misses == 1

    service.create_snapshot(request)
    stats = service.cache_stats()
    assert stats["fx"].hits == 1
    assert stats["fx"].misses == 1


def test_port_args_take_precedence_over_adapter_args(commodity_adapter, tax_adapter):
    """Test that when both adapter and port args are provided, port takes precedence."""
    fx_adapter_1 = InMemoryFXAdapter({"EUR": Decimal("0.93")})
    fx_adapter_2 = InMemoryFXAdapter({"GBP": Decimal("0.79")})

    with pytest.warns(DeprecationWarning):
        service = DataSnapshotService(
            fx_adapter=fx_adapter_1,
            fx_port=fx_adapter_2,  # This should be used
            commodity_adapter=commodity_adapter,
            tax_adapter=tax_adapter,
        )

    snapshot = service.build_snapshot(
        base_currency="USD",
        commodity_symbols=[],
    )
    
    # Should have 1 FX rate from fx_adapter_2 (GBP), not 2 from fx_adapter_1 (EUR)
    assert len(snapshot.fx_rates) == 1
    assert snapshot.fx_rates[0].quote_currency == "GBP"


def test_build_snapshot_rejects_blank_base_currency(
    fx_adapter, commodity_adapter, tax_adapter
):
    """Ensure callers receive clear feedback when base currency is invalid."""

    with pytest.warns(DeprecationWarning):
        service = DataSnapshotService(
            fx_adapter=fx_adapter,
            commodity_adapter=commodity_adapter,
            tax_adapter=tax_adapter,
        )

    with pytest.raises(ValueError, match="base_currency"):
        service.build_snapshot(
            base_currency="  ",
            commodity_symbols=["XAU"],
        )


def test_build_snapshot_deduplicates_symbols_and_jurisdictions(
    fx_adapter, tax_adapter
):
    """Commodity and tax scopes should be normalised before adapter access."""

    commodity_adapter = RecordingCommodityAdapter({"XAU": Decimal("2034.23")})
    with pytest.warns(DeprecationWarning):
        service = DataSnapshotService(
            fx_adapter=fx_adapter,
            commodity_adapter=commodity_adapter,
            tax_adapter=tax_adapter,
        )

    snapshot = service.build_snapshot(
        base_currency="usd",
        commodity_symbols=["XAU", "xau", "", "XAU"],
        jurisdictions=["us-ca", "us-ca", "  "],
    )

    assert snapshot.tax_rules  # Jurisdiction filtered to just one entry
    assert commodity_adapter.seen == [("XAU",)]


def test_create_snapshot_reuses_cached_adapter_calls():
    """Subsequent requests with identical scopes reuse cached adapter responses."""

    fx = CountingFXAdapter({"EUR": Decimal("0.93")})
    commodity = RecordingCommodityAdapter({"XAU": Decimal("2034.23")})
    tax = CountingTaxAdapter(
        (
            TaxRule(
                jurisdiction="us-ca",
                rate=Decimal("0.0825"),
                description="California sales tax",
                effective_from=date(2024, 1, 1),
            ),
        )
    )

    with pytest.warns(DeprecationWarning):
        service = DataSnapshotService(
            fx_adapter=fx,
            commodity_adapter=commodity,
            tax_adapter=tax,
        )

    request = SnapshotRequest.from_primitives(
        base_currency="USD",
        commodity_symbols=["XAU"],
        jurisdictions=["us-ca"],
    )

    service.create_snapshot(request)
    service.create_snapshot(request)

    assert fx.calls == 1
    assert commodity.seen == [("XAU",)]
    assert tax.requested == ["us-ca"]
