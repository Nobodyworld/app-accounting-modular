from datetime import date

from plugins.bank_plaid.provider import PlaidBankProvider


def test_plaid_provider_lists_accounts() -> None:
    provider = PlaidBankProvider()
    accounts = provider.list_accounts()
    assert accounts
    assert accounts[0]["id"] == "acc_001"
    assert float(accounts[0]["balance"]) > 0


def test_plaid_provider_fetches_transactions() -> None:
    provider = PlaidBankProvider()
    txns = list(provider.fetch_transactions("acc_001", date(2024, 1, 1), date(2024, 1, 10)))
    assert txns
    assert txns[0]["account_id"] == "acc_001"
    assert "description" in txns[0]
