"""Shared snapshot rendering utilities for CLI commands."""

from __future__ import annotations

from dataclasses import asdict
from typing import Sequence

from apps.modular_accounting.application import (
    DataSnapshot,
    ScenarioBatchResult,
    SnapshotDiagnostics,
)

__all__ = [
    "format_snapshot_table",
    "format_scenario_batch_table",
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


def format_scenario_batch_table(batch: ScenarioBatchResult) -> str:
    """Render a scenario batch result as a human-readable report."""

    sections: list[str] = []
    summary = batch.summary
    summary_rows = [
        ("Scenarios", str(summary.scenario_count)),
        ("Base currencies", ", ".join(summary.base_currencies) or "-"),
        ("Commodity symbols", ", ".join(summary.commodity_symbols) or "-"),
        ("Jurisdictions", ", ".join(summary.jurisdictions) or "-"),
        ("Total FX rates", str(summary.total_fx_rates)),
        ("Total commodity quotes", str(summary.total_commodity_quotes)),
        ("Total tax rules", str(summary.total_tax_rules)),
        (
            "Max FX age (s)",
            "-" if summary.max_fx_age_seconds is None else f"{summary.max_fx_age_seconds:.0f}",
        ),
        (
            "Max commodity age (s)",
            "-"
            if summary.max_commodity_age_seconds is None
            else f"{summary.max_commodity_age_seconds:.0f}",
        ),
        ("Max active tax rules", str(summary.max_active_tax_rules)),
    ]
    sections.append("Scenario Summary")
    sections.append("----------------")
    sections.extend(_render_table(("Metric", "Value"), summary_rows))

    sections.append("")
    sections.append("Scenario Diagnostics")
    sections.append("--------------------")
    if batch.results:
        diag_rows = [
            (
                result.scenario.name,
                result.diagnostics.base_currency or result.scenario.base_currency,
                str(result.diagnostics.fx_rate_count),
                str(result.diagnostics.commodity_quote_count),
                str(result.diagnostics.tax_rule_count),
                ", ".join(result.diagnostics.missing_sections) or "None",
            )
            for result in batch.results
        ]
        sections.extend(
            _render_table(
                ("Scenario", "Base", "FX", "Commodities", "Tax", "Missing"),
                diag_rows,
            )
        )
    else:
        sections.append("(no scenarios)")

    if summary.missing_sections:
        sections.append("")
        sections.append("Missing Sections")
        sections.append("----------------")
        missing_rows = [
            (name, ", ".join(sections_) if sections_ else "-")
            for name, sections_ in summary.missing_sections.items()
        ]
        sections.extend(_render_table(("Scenario", "Sections"), missing_rows))

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
