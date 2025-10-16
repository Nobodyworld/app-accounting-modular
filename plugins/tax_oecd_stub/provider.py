from typing import List
from datetime import date
from apps.api.models.models import TaxRule

class OECDFakeTaxProvider:
    name = "oecd_stub"
    # # TODO: Replace with real OECD/OIPA pulls and country-specific loaders
    def upsert_rules(self) -> List[TaxRule]:
        # Demo rules: EU VAT baseline stub and US corporate federal baseline stub
        return [
            TaxRule(jurisdiction="EU", scope="vat", expression="rate=0.20", valid_from=date(2020,1,1), source="stub://oecd"),
            TaxRule(jurisdiction="US-FED", scope="corporate_income", expression="rate=0.21", valid_from=date(2018,1,1), source="stub://us-fed")
        ]

def provider():
    return OECDFakeTaxProvider()
