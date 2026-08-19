"""Stub provider emitting US Federal and State tax rules."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from apps.api.models.models import TaxRule
from apps.provider_sdk import ProviderManifest

__version__ = "0.3.0"

PROVIDER_MANIFEST = ProviderManifest(
    key="tax:us_tables",
    name="Illustrative US Tax Tables",
    version=__version__,
    api_major=0,
    capabilities=("tax",),
    description="Deterministic illustrative US tax-table sample adapter.",
    license="Apache-2.0",
    network_policy="none",
    data_classification="controlled-sample",
)


class USTaxTableProvider:
    """Provide basic US Federal and State tax rules."""

    name = "us_tax_tables_stub"

    def upsert_rules(self) -> Iterable[TaxRule]:
        today = date.today()
        yield TaxRule(
            jurisdiction="US-FED",
            scope="income",
            expression='{"rate": 0.21}',
            valid_from=today.replace(month=1, day=1),
            source=self.name,
            precedence=50,
            rule_metadata={"description": "Federal corporate income"},
        )
        yield TaxRule(
            jurisdiction="US-CA",
            scope="income",
            expression='{"rate": 0.0884}',
            valid_from=today.replace(month=1, day=1),
            source=self.name,
            precedence=60,
            rule_metadata={"description": "California corporate income"},
        )
        yield TaxRule(
            jurisdiction="US-NY",
            scope="income",
            expression='{"rate": 0.0785}',
            valid_from=today.replace(month=1, day=1),
            source=self.name,
            precedence=60,
            rule_metadata={"description": "New York corporate income"},
        )


def provider() -> USTaxTableProvider:
    return USTaxTableProvider()
