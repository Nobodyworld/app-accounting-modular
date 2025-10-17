"""Stub implementation for tax rule ingestion."""

from __future__ import annotations

from datetime import date
from typing import Iterable

from apps.api.models.models import TaxRule

__all__ = ["OECDFakeTaxProvider", "provider"]


class OECDFakeTaxProvider:
    """Return a static set of sample tax rules."""

    name = "oecd_stub"

    def upsert_rules(self) -> Iterable[TaxRule]:
        return [
            TaxRule(
                jurisdiction="EU",
                scope="vat",
                expression="rate=0.20",
                valid_from=date(2020, 1, 1),
                source="stub://oecd",
            ),
            TaxRule(
                jurisdiction="US-FED",
                scope="corporate_income",
                expression="rate=0.21",
                valid_from=date(2018, 1, 1),
                source="stub://us-fed",
            ),
        ]


def provider() -> OECDFakeTaxProvider:
    """Entry point for the plugin loader."""

    return OECDFakeTaxProvider()
