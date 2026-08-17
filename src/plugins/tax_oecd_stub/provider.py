"""Stub implementation for tax rule ingestion."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from apps.api.models.models import TaxRule
from apps.provider_sdk import ProviderManifest

__all__ = ["OECDFakeTaxProvider", "PROVIDER_MANIFEST", "provider"]
__version__ = "0.3.0"

PROVIDER_MANIFEST = ProviderManifest(
    key="tax:oecd_demo",
    name="OECD-style Tax Rules Demo",
    version=__version__,
    api_major=0,
    capabilities=("tax",),
    description="Deterministic OECD-style tax-rule sample adapter.",
    license="Apache-2.0",
    network_policy="none",
    data_classification="controlled-sample",
)


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
