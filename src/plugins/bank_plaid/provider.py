"""Plaid integration stub for bank feeds.

This provider is intentionally lightweight; it mimics Plaid-like responses so
the rest of the system can exercise bank feed plumbing without live API keys.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable


class PlaidBankProvider:
    """Return stubbed accounts and transactions for reconciliation flows."""

    name = "plaid_stub"

    def list_accounts(self) -> list[dict[str, str | float]]:
        return [
            {"id": "acc_001", "name": "Operating Checking", "mask": "1234", "type": "depository", "balance": 125000.50},
            {"id": "acc_002", "name": "Savings", "mask": "9876", "type": "savings", "balance": 50000.00},
        ]

    def fetch_transactions(self, account_id: str, start: date, end: date) -> Iterable[dict[str, str | float]]:
        current = start
        idx = 0
        while current <= end:
            amount = (-1) ** idx * (50 + idx)
            yield {
                "account_id": account_id,
                "date": current.isoformat(),
                "amount": amount,
                "description": f"Stub transaction {idx}",
            }
            idx += 1
            current += timedelta(days=3)


def provider() -> PlaidBankProvider:
    return PlaidBankProvider()
