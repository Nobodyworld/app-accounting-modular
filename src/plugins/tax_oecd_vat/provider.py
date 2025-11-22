"""Stub VAT provider using illustrative OECD VAT rates."""

from __future__ import annotations

from datetime import date
from typing import Iterable

from apps.api.models.models import TaxRule


class OECDEVATProvider:
    """Emit VAT rules for a handful of jurisdictions."""

    name = "oecd_vat_stub"

    def upsert_rules(self) -> Iterable[TaxRule]:
        today = date.today()
        yield TaxRule(
            jurisdiction="EU-FR",
            scope="vat",
            expression={"rate": 0.20},
            valid_from=today.replace(month=1, day=1),
            source=self.name,
            precedence=100,
            rule_metadata={"description": "Standard VAT France"},
        )
        yield TaxRule(
            jurisdiction="EU-DE",
            scope="vat",
            expression={"rate": 0.19},
            valid_from=today.replace(month=1, day=1),
            source=self.name,
            precedence=100,
            rule_metadata={"description": "Standard VAT Germany"},
        )
        yield TaxRule(
            jurisdiction="EU-IE",
            scope="vat",
            expression={"rate": 0.23},
            valid_from=today.replace(month=1, day=1),
            source=self.name,
            precedence=100,
            rule_metadata={"description": "Standard VAT Ireland"},
        )


def provider() -> OECDEVATProvider:
    return OECDEVATProvider()
