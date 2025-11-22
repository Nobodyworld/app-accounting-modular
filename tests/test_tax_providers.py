from plugins.tax_oecd_vat.provider import OECDEVATProvider
from plugins.tax_us_tables.provider import USTaxTableProvider


def test_oecd_vat_provider_emits_multiple_rules() -> None:
    provider = OECDEVATProvider()
    rules = list(provider.upsert_rules())
    assert len(rules) >= 3
    assert {rule.jurisdiction for rule in rules} >= {"EU-FR", "EU-DE", "EU-IE"}
    assert all(rule.scope == "vat" for rule in rules)


def test_us_tax_table_provider_emits_federal_and_states() -> None:
    provider = USTaxTableProvider()
    rules = list(provider.upsert_rules())
    jurisdictions = {rule.jurisdiction for rule in rules}
    assert "US-FED" in jurisdictions
    assert "US-CA" in jurisdictions
    assert "US-NY" in jurisdictions
    assert all(rule.scope == "income" for rule in rules)
