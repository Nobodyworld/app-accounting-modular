from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from apps.modular_accounting.adapters import (
    InMemoryCommodityAdapter,
    InMemoryFXAdapter,
    InMemoryTaxAdapter,
)
from apps.modular_accounting.domain import LedgerEntry, Money, TaxRule, Transaction


def test_transaction_balance_control_passes_for_balanced_entries() -> None:
    transaction = Transaction(
        transaction_id="txn-001",
        occurred_on=date(2026, 1, 1),
        description="Balanced journal",
        entries=[
            LedgerEntry(
                account_code="1000",
                amount=Money(amount=Decimal("250.00"), currency="USD"),
                direction="debit",
            ),
            LedgerEntry(
                account_code="4000",
                amount=Money(amount=Decimal("250.00"), currency="USD"),
                direction="credit",
            ),
        ],
    )

    assert transaction.is_balanced() is True


def test_transaction_balance_control_fails_for_unbalanced_entries() -> None:
    transaction = Transaction(
        transaction_id="txn-002",
        occurred_on=date(2026, 1, 1),
        description="Unbalanced journal",
        entries=[
            LedgerEntry(
                account_code="5000",
                amount=Money(amount=Decimal("100.00"), currency="USD"),
                direction="debit",
            ),
            LedgerEntry(
                account_code="2000",
                amount=Money(amount=Decimal("90.00"), currency="USD"),
                direction="credit",
            ),
        ],
    )

    assert transaction.is_balanced() is False


def test_empty_transaction_is_not_balanced() -> None:
    transaction = Transaction(
        transaction_id="txn-empty",
        occurred_on=date(2026, 1, 1),
        description="Empty journal",
    )

    assert transaction.is_balanced() is False


def test_single_entry_transaction_is_not_balanced() -> None:
    transaction = Transaction(
        transaction_id="txn-single",
        occurred_on=date(2026, 1, 1),
        description="Single entry",
        entries=[
            LedgerEntry(
                account_code="1000",
                amount=Money(amount=Decimal("10.00"), currency="USD"),
                direction="debit",
            )
        ],
    )

    assert transaction.is_balanced() is False


def test_ledger_entry_rejects_invalid_direction() -> None:
    with pytest.raises(ValueError, match="direction"):
        LedgerEntry(
            account_code="1000",
            amount=Money(amount=Decimal("10.00"), currency="USD"),
            direction="increase",
        )


def test_ledger_entry_rejects_non_positive_amount() -> None:
    with pytest.raises(ValueError, match="positive"):
        LedgerEntry(
            account_code="1000",
            amount=Money(amount=Decimal("0"), currency="USD"),
            direction="debit",
        )


def test_cross_currency_offset_is_not_balanced() -> None:
    transaction = Transaction(
        transaction_id="txn-currency",
        occurred_on=date(2026, 1, 1),
        description="Cross-currency offset",
        entries=[
            LedgerEntry(
                account_code="1000",
                amount=Money(amount=Decimal("100.00"), currency="USD"),
                direction="debit",
            ),
            LedgerEntry(
                account_code="4000",
                amount=Money(amount=Decimal("100.00"), currency="EUR"),
                direction="credit",
            ),
        ],
    )

    assert transaction.is_balanced() is False


def test_each_currency_can_balance_independently() -> None:
    transaction = Transaction(
        transaction_id="txn-multi-currency",
        occurred_on=date(2026, 1, 1),
        description="Balanced currency groups",
        entries=[
            LedgerEntry("1000", Money(Decimal("100.00"), "USD"), "debit"),
            LedgerEntry("4000", Money(Decimal("100.00"), "USD"), "credit"),
            LedgerEntry("1100", Money(Decimal("80.00"), "EUR"), "debit"),
            LedgerEntry("4100", Money(Decimal("80.00"), "EUR"), "credit"),
        ],
    )

    assert transaction.is_balanced() is True


def test_transaction_accounts_control_tracks_all_accounts_in_order() -> None:
    transaction = Transaction(
        transaction_id="txn-003",
        occurred_on=date(2026, 1, 2),
        description="Account traceability",
    )

    transaction.add_entry(
        LedgerEntry(
            account_code="1000",
            amount=Money(amount=Decimal("10.00"), currency="USD"),
            direction="debit",
        )
    )
    transaction.add_entry(
        LedgerEntry(
            account_code="2100",
            amount=Money(amount=Decimal("10.00"), currency="USD"),
            direction="credit",
        )
    )

    assert list(transaction.accounts()) == ["1000", "2100"]


def test_financial_data_control_filters_unknown_commodity_symbols() -> None:
    adapter = InMemoryCommodityAdapter({"XAU": Decimal("2345.10")}, currency="USD")

    quotes = list(adapter.get_quotes(["XAU", "XAG"]))

    assert len(quotes) == 1
    assert quotes[0].symbol == "XAU"
    assert quotes[0].price.currency == "USD"


def test_financial_data_control_retains_fx_pair_context() -> None:
    adapter = InMemoryFXAdapter({"EUR": Decimal("0.91"), "GBP": Decimal("0.78")})

    rates = list(adapter.get_rates("USD"))

    assert {rate.base_currency for rate in rates} == {"USD"}
    assert {rate.quote_currency for rate in rates} == {"EUR", "GBP"}


def test_financial_data_control_filters_tax_rules_by_jurisdiction() -> None:
    adapter = InMemoryTaxAdapter(
        [
            TaxRule(
                jurisdiction="us",
                rate=Decimal("0.07"),
                description="US sales tax",
                effective_from=date(2025, 1, 1),
            ),
            TaxRule(
                jurisdiction="uk",
                rate=Decimal("0.20"),
                description="UK VAT",
                effective_from=date(2025, 1, 1),
            ),
        ]
    )

    us_rules = list(adapter.get_rules("us"))
    all_rules = list(adapter.get_rules())

    assert len(us_rules) == 1
    assert us_rules[0].jurisdiction == "us"
    assert len(all_rules) == 2
