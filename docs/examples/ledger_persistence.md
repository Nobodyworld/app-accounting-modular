# Persisting Domain Transactions to External Ledgers

These snippets demonstrate how to translate modular-accounting domain transactions into payloads accepted by common ledgers. They are intentionally lightweight and avoid SDK dependencies so you can adapt them to any REST client.

## QuickBooks-style Journal Entry

```python
from decimal import Decimal
import requests

transaction = {
    "date": "2025-02-01",
    "description": "Invoice payment",
    "postings": [
        {"account_code": "1100", "debit": Decimal("250.00"), "credit": Decimal("0.00"), "currency": "USD"},
        {"account_code": "4000", "debit": Decimal("0.00"), "credit": Decimal("250.00"), "currency": "USD"},
    ],
}

def to_quickbooks_payload(txn: dict) -> dict:
    return {
        "TxnDate": txn["date"],
        "PrivateNote": txn["description"],
        "Line": [
            {
                "DetailType": "JournalEntryLineDetail",
                "Amount": float(p["debit"] or p["credit"]),
                "Description": txn["description"],
                "JournalEntryLineDetail": {
                    "PostingType": "Debit" if p["debit"] else "Credit",
                    "AccountRef": {"value": p["account_code"]},
                },
            }
            for p in txn["postings"]
        ],
    }

payload = to_quickbooks_payload(transaction)
requests.post(
    "https://quickbooks.api.intuit.com/v3/company/{company_id}/journalentry",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    json=payload,
)
```

## Xero / Generic Ledger JSON

```python
def to_xero_payload(txn: dict) -> dict:
    return {
        "Date": txn["date"],
        "Narration": txn["description"],
        "LineItems": [
            {
                "Description": txn["description"],
                "AccountCode": p["account_code"],
                "LineAmount": float(p["debit"] or -p["credit"]),
                "TaxType": "NONE",
            }
            for p in txn["postings"]
        ],
    }
```

## SQL Upsert for a Custom Ledger

```sql
-- accounts table: (code TEXT PRIMARY KEY, name TEXT, currency TEXT)
-- transactions table: (id INTEGER PK, date TEXT, description TEXT)
-- postings table: (tx_id INTEGER, account_code TEXT, debit NUMERIC, credit NUMERIC, currency TEXT)

BEGIN;
INSERT INTO transactions (date, description) VALUES (:date, :description);
INSERT INTO postings (tx_id, account_code, debit, credit, currency)
VALUES
(:tx_id, :acct1, :debit1, :credit1, :currency),
(:tx_id, :acct2, :debit2, :credit2, :currency);
COMMIT;
```

These examples are intentionally minimal: adapt authentication, error handling, and retries to your chosen provider or data warehouse.
