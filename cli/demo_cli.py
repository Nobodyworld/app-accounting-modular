"""Demonstration CLI for the modular accounting adapters."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Iterable, Sequence

import click

from apps.modular_accounting.adapters import (
    InMemoryCommodityAdapter,
    InMemoryFXAdapter,
    InMemoryTaxAdapter,
)
from apps.modular_accounting.application import DataSnapshot, DataSnapshotService
from apps.modular_accounting.domain import TaxRule


def _seed_tax_rules() -> Iterable[TaxRule]:
    """Return demo tax rules covering multiple jurisdictions.

    Returns
    -------
    Iterable[TaxRule]
        Reference tax rules used by the demo CLI.
    """

    effective = date(2024, 1, 1)
    return (
        TaxRule(
            jurisdiction="us-ca",
            rate=Decimal("0.0825"),
            description="California statewide sales tax",
            effective_from=effective,
        ),
        TaxRule(
            jurisdiction="uk",
            rate=Decimal("0.2000"),
            description="United Kingdom VAT",
            effective_from=effective,
        ),
    )


@click.group()
def demo() -> None:
    """Commands showcasing the adapter orchestration layer."""


def _render_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    """Return formatted table lines with padded columns."""

    widths = [len(header) for header in headers]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    template = "  ".join(f"{{:<{width}}}" for width in widths)
    divider = "  ".join("-" * width for width in widths)
    lines = [template.format(*headers), divider]
    lines.extend(template.format(*row) for row in rows)
    return lines


def _format_snapshot_table(snapshot: DataSnapshot) -> str:
    """Format snapshot data as a multi-section text table."""

    sections: list[str] = []

    sections.append("FX Rates")
    sections.append("--------")
    if snapshot.fx_rates:
        fx_rows = [
            (
                rate.base_currency,
                rate.quote_currency,
                f"{rate.rate}",
                rate.as_of.isoformat(),
            )
            for rate in snapshot.fx_rates
        ]
        sections.extend(
            _render_table(("Base", "Quote", "Rate", "As Of"), fx_rows)
        )
    else:
        sections.append("(no FX rates)")

    sections.append("")
    sections.append("Commodity Quotes")
    sections.append("-----------------")
    if snapshot.commodity_quotes:
        commodity_rows = [
            (
                quote.symbol,
                quote.price.currency,
                f"{quote.price.amount}",
                quote.as_of.isoformat(),
            )
            for quote in snapshot.commodity_quotes
        ]
        sections.extend(
            _render_table(("Symbol", "Currency", "Amount", "As Of"), commodity_rows)
        )
    else:
        sections.append("(no commodity quotes)")

    sections.append("")
    sections.append("Tax Rules")
    sections.append("---------")
    if snapshot.tax_rules:
        tax_rows = [
            (
                rule.jurisdiction,
                f"{rule.rate}",
                rule.description,
                rule.effective_from.isoformat(),
                rule.effective_to.isoformat() if rule.effective_to else "-",
            )
            for rule in snapshot.tax_rules
        ]
        sections.extend(
            _render_table(
                ("Jurisdiction", "Rate", "Description", "Effective From", "Effective To"),
                tax_rows,
            )
        )
    else:
        sections.append("(no tax rules)")

    return "\n".join(sections)


@demo.command()
@click.option("--base", "base_currency", default="USD", show_default=True)
@click.option(
    "--commodity",
    "commodity_symbols",
    multiple=True,
    default=("XAU", "XAG"),
    show_default=True,
)
@click.option(
    "--jurisdiction",
    "jurisdictions",
    multiple=True,
    help="Limit tax rules to specific jurisdictions.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "table"], case_sensitive=False),
    default="json",
    show_default=True,
    help="Choose between structured JSON or human-readable table output.",
)
def snapshot(
    base_currency: str,
    commodity_symbols: tuple[str, ...],
    jurisdictions: tuple[str, ...],
    output_format: str,
) -> None:
    """Generate a JSON snapshot from the in-memory adapters.

    Parameters
    ----------
    base_currency:
        Currency code used to request FX rates.
    commodity_symbols:
        Commodity symbols to include in the snapshot.
    jurisdictions:
        Jurisdictions used to filter tax rules when provided.
    """

    fx_adapter = InMemoryFXAdapter({"EUR": Decimal("0.93"), "GBP": Decimal("0.79")})
    commodity_adapter = InMemoryCommodityAdapter({"XAU": Decimal("2034.23"), "XAG": Decimal("24.83")})
    tax_adapter = InMemoryTaxAdapter(_seed_tax_rules())
    service = DataSnapshotService(fx_adapter, commodity_adapter, tax_adapter)

    try:
        snapshot = service.build_snapshot(
            base_currency=base_currency,
            commodity_symbols=commodity_symbols,
            jurisdictions=jurisdictions or None,
        )
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="--base") from exc

    if output_format.lower() == "json":
        payload = {
            "fx_rates": [
                {
                    "base_currency": rate.base_currency,
                    "quote_currency": rate.quote_currency,
                    "rate": str(rate.rate),
                    "as_of": rate.as_of.isoformat(),
                }
                for rate in snapshot.fx_rates
            ],
            "commodity_quotes": [
                {
                    "symbol": quote.symbol,
                    "price": {
                        "amount": str(quote.price.amount),
                        "currency": quote.price.currency,
                    },
                    "as_of": quote.as_of.isoformat(),
                }
                for quote in snapshot.commodity_quotes
            ],
            "tax_rules": [
                {
                    "jurisdiction": rule.jurisdiction,
                    "rate": str(rule.rate),
                    "description": rule.description,
                    "effective_from": rule.effective_from.isoformat(),
                    "effective_to": rule.effective_to.isoformat()
                    if rule.effective_to
                    else None,
                }
                for rule in snapshot.tax_rules
            ],
        }
        click.echo(json.dumps(payload, indent=2))
        return

    click.echo(_format_snapshot_table(snapshot))
