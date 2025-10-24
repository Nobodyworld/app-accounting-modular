"""Tests for DataSnapshotService with legacy and new keyword argument names."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from apps.modular_accounting.adapters import (
    InMemoryCommodityAdapter,
    InMemoryFXAdapter,
    InMemoryTaxAdapter,
)
from apps.modular_accounting.domain import TaxRule
from apps.modular_accounting.services import DataSnapshotService


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
    service = DataSnapshotService(
        fx_adapter=fx_adapter,
        commodity_port=commodity_adapter,
        tax_adapter=tax_adapter,
    )
    assert service is not None


def test_init_raises_without_fx(commodity_adapter, tax_adapter):
    """Test DataSnapshotService raises TypeError when FX adapter is missing."""
    with pytest.raises(TypeError, match="fx_adapter or fx_port"):
        DataSnapshotService(
            commodity_adapter=commodity_adapter,
            tax_adapter=tax_adapter,
        )


def test_init_raises_without_commodity(fx_adapter, tax_adapter):
    """Test DataSnapshotService raises TypeError when commodity adapter is missing."""
    with pytest.raises(TypeError, match="commodity_adapter or commodity_port"):
        DataSnapshotService(
            fx_adapter=fx_adapter,
            tax_adapter=tax_adapter,
        )


def test_init_raises_without_tax(fx_adapter, commodity_adapter):
    """Test DataSnapshotService raises TypeError when tax adapter is missing."""
    with pytest.raises(TypeError, match="tax_adapter or tax_port"):
        DataSnapshotService(
            fx_adapter=fx_adapter,
            commodity_adapter=commodity_adapter,
        )


def test_build_snapshot_with_legacy_args(fx_adapter, commodity_adapter, tax_adapter):
    """Test build_snapshot works correctly with legacy keyword args."""
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


def test_port_args_take_precedence_over_adapter_args(commodity_adapter, tax_adapter):
    """Test that when both adapter and port args are provided, port takes precedence."""
    fx_adapter_1 = InMemoryFXAdapter({"EUR": Decimal("0.93")})
    fx_adapter_2 = InMemoryFXAdapter({"GBP": Decimal("0.79")})
    
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
