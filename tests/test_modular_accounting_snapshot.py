from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime
from decimal import Decimal

from apps.modular_accounting.application import DataSnapshotService, SnapshotRequest
from apps.modular_accounting.domain import CommodityQuote, FXRate, Money, TaxRule


class FXPortStub:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_rates(self, base_currency: str) -> Iterable[FXRate]:
        self.calls.append(base_currency)
        return (
            FXRate(
                base_currency=base_currency,
                quote_currency="EUR",
                rate=Decimal("0.92"),
                as_of=datetime(2024, 1, 1, 12, 0, 0),
            ),
        )


class CommodityPortStub:
    def __init__(self) -> None:
        self.calls: list[Sequence[str]] = []

    def get_quotes(self, symbols: Sequence[str]) -> Iterable[CommodityQuote]:
        self.calls.append(tuple(symbols))
        return (
            CommodityQuote(
                symbol="XAU",
                price=Money(amount=Decimal("2040.11"), currency="USD"),
                as_of=datetime(2024, 1, 1, 12, 0, 0),
            ),
        )


class TaxPortStub:
    def __init__(self) -> None:
        self.calls: list[str | None] = []

    def get_rules(self, jurisdiction: str | None = None) -> Iterable[TaxRule]:
        self.calls.append(jurisdiction)
        return (
            TaxRule(
                jurisdiction=jurisdiction or "global",
                rate=Decimal("0.20"),
                description="VAT",
                effective_from=date(2024, 1, 1),
                effective_to=None,
            ),
        )


def test_build_snapshot_aggregates_all_ports() -> None:
    fx_port = FXPortStub()
    commodity_port = CommodityPortStub()
    tax_port = TaxPortStub()

    service = DataSnapshotService(
        fx_port=fx_port,
        commodity_port=commodity_port,
        tax_port=tax_port,
    )

    snapshot = service.build_snapshot(
        base_currency="USD",
        commodity_symbols=("XAU", "XAG"),
        jurisdictions=("us", "uk"),
    )

    assert fx_port.calls == ["USD"]
    assert commodity_port.calls == [("XAU", "XAG")]
    assert tax_port.calls == ["us", "uk"]

    assert len(snapshot.fx_rates) == 1
    assert snapshot.fx_rates[0].quote_currency == "EUR"
    assert len(snapshot.commodity_quotes) == 1
    assert snapshot.commodity_quotes[0].symbol == "XAU"
    assert len(snapshot.tax_rules) == 2


def test_build_snapshot_supports_default_tax_scope() -> None:
    fx_port = FXPortStub()
    commodity_port = CommodityPortStub()
    tax_port = TaxPortStub()

    service = DataSnapshotService(
        fx_port=fx_port,
        commodity_port=commodity_port,
        tax_port=tax_port,
    )

    service.build_snapshot(
        base_currency="USD",
        commodity_symbols=[],
        jurisdictions=None,
    )

    assert tax_port.calls == [None]


def test_build_snapshot_skips_tax_calls_for_empty_scope() -> None:
    fx_port = FXPortStub()
    commodity_port = CommodityPortStub()
    tax_port = TaxPortStub()

    service = DataSnapshotService(
        fx_port=fx_port,
        commodity_port=commodity_port,
        tax_port=tax_port,
    )

    snapshot = service.build_snapshot(
        base_currency="USD",
        commodity_symbols=[],
        jurisdictions=(),
    )

    assert tax_port.calls == []
    assert snapshot.tax_rules == ()


def test_build_snapshot_skips_commodity_port_for_empty_symbols() -> None:
    fx_port = FXPortStub()
    commodity_port = CommodityPortStub()
    tax_port = TaxPortStub()

    service = DataSnapshotService(
        fx_port=fx_port,
        commodity_port=commodity_port,
        tax_port=tax_port,
    )

    snapshot = service.build_snapshot(
        base_currency="USD",
        commodity_symbols=(),
        jurisdictions=None,
    )

    assert commodity_port.calls == []
    assert snapshot.commodity_quotes == ()


def test_create_snapshot_accepts_prebuilt_request() -> None:
    fx_port = FXPortStub()
    commodity_port = CommodityPortStub()
    tax_port = TaxPortStub()

    service = DataSnapshotService(
        fx_port=fx_port,
        commodity_port=commodity_port,
        tax_port=tax_port,
    )

    request = SnapshotRequest(
        base_currency="USD",
        commodity_symbols=("XAU",),
        jurisdictions=("us", "us"),
    )
    snapshot = service.create_snapshot(request)

    # Ensure duplicate jurisdictions only trigger one adapter call.
    assert tax_port.calls == ["us"]
    assert len(snapshot.tax_rules) == 1
