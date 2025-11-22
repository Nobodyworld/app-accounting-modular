"""Stub provider emitting US Federal and State tax rules."""

from __future__ import annotations

from datetime import date
from typing import Iterable

from apps.api.models.models import TaxRule


class USTaxTableProvider:
    """Provide basic US Federal and State tax rules."""

    name = "us_tax_tables_stub"

    def upsert_rules(self) -> Iterable[TaxRule]:
        today = date.today()
        yield TaxRule(
            jurisdiction="US-FED",
            scope="income",
            expression={"rate": 0.21},
            valid_from=today.replace(month=1, day=1),
            source=self.name,
            precedence=50,
            rule_metadata={"description": "Federal corporate income"},
        )
        yield TaxRule(
            jurisdiction="US-CA",
            scope="income",
            expression={"rate": 0.0884},
            valid_from=today.replace(month=1, day=1),
            source=self.name,
            precedence=60,
            rule_metadata={"description": "California corporate income"},
        )
        yield TaxRule(
            jurisdiction="US-NY",
            scope="income",
            expression={"rate": 0.0785},
            valid_from=today.replace(month=1, day=1),
            source=self.name,
            precedence=60,
            rule_metadata={"description": "New York corporate income"},
        )


def provider() -> USTaxTableProvider:
    return USTaxTableProvider()
