"""Demonstration CLI for the modular accounting adapters."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Iterable

import click

from apps.modular_accounting.adapters import (
    InMemoryCommodityAdapter,
    InMemoryFXAdapter,
    InMemoryTaxAdapter,
)
from apps.modular_accounting.application import DataSnapshot, DataSnapshotService
from apps.modular_accounting.domain import TaxRule
from cli.snapshot_render import format_snapshot_table, snapshot_to_payload


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
        payload = snapshot_to_payload(snapshot)
        click.echo(json.dumps(payload, indent=2, default=str))
        return

    click.echo(format_snapshot_table(snapshot))
