"""Shared snapshot rendering utilities for CLI commands."""

from __future__ import annotations

from dataclasses import asdict
from typing import Sequence

from apps.modular_accounting.application import (
    DataSnapshot,
    SnapshotDiagnostics,
)

__all__ = [
    "format_snapshot_table",
    "snapshot_to_payload",
]


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


def format_snapshot_table(
    snapshot: DataSnapshot, diagnostics: SnapshotDiagnostics | None = None
) -> str:
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
        sections.extend(_render_table(("Base", "Quote", "Rate", "As Of"), fx_rows))
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

    if diagnostics is not None:
        sections.append("")
        sections.append("Diagnostics")
        sections.append("-----------")
        diag_rows = [
            ("Base currency", diagnostics.base_currency or "-"),
            ("FX pairs", ", ".join(diagnostics.fx_pairs) or "-"),
            (
                "FX count",
                str(diagnostics.fx_rate_count),
            ),
            (
                "FX max age (s)",
                "-" if diagnostics.fx_max_age_seconds is None else f"{diagnostics.fx_max_age_seconds:.0f}",
            ),
            (
                "Commodity symbols",
                ", ".join(diagnostics.commodity_symbols) or "-",
            ),
            (
                "Commodity count",
                str(diagnostics.commodity_quote_count),
            ),
            (
                "Commodity max age (s)",
                "-"
                if diagnostics.commodity_max_age_seconds is None
                else f"{diagnostics.commodity_max_age_seconds:.0f}",
            ),
            (
                "Tax jurisdictions",
                ", ".join(diagnostics.tax_jurisdictions) or "-",
            ),
            ("Tax rule count", str(diagnostics.tax_rule_count)),
            (
                "Active tax rules",
                str(diagnostics.active_tax_rule_count),
            ),
            (
                "Missing sections",
                ", ".join(diagnostics.missing_sections) or "None",
            ),
        ]
        sections.extend(_render_table(("Metric", "Value"), diag_rows))

    return "\n".join(sections)


def snapshot_to_payload(
    snapshot: DataSnapshot, diagnostics: SnapshotDiagnostics | None = None
) -> dict[str, object]:
    """Convert snapshot data into a JSON-serialisable payload."""

    payload = {
        "fx_rates": [
            {
                "base_currency": rate.base_currency,
                "quote_currency": rate.quote_currency,
                "rate": rate.rate,
                "as_of": rate.as_of,
            }
            for rate in snapshot.fx_rates
        ],
        "commodity_quotes": [
            {
                "symbol": quote.symbol,
                "price": asdict(quote.price),
                "as_of": quote.as_of,
            }
            for quote in snapshot.commodity_quotes
        ],
        "tax_rules": [
            {
                "jurisdiction": rule.jurisdiction,
                "rate": rule.rate,
                "description": rule.description,
                "effective_from": rule.effective_from,
                "effective_to": rule.effective_to,
            }
            for rule in snapshot.tax_rules
        ],
    }
    if diagnostics is not None:
        payload["diagnostics"] = asdict(diagnostics)
    return payload
