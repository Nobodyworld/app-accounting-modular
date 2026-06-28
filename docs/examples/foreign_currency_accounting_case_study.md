# Foreign Currency Accounting Case Study

This case study demonstrates how to keep journal postings balanced and auditable
when transaction currency differs from the ledger presentation currency.

## Scenario

- Functional/presentation currency: USD
- Supplier invoice currency: EUR
- Invoice amount: EUR 10,000
- Spot rate on invoice date (2026-05-10): 1 EUR = 1.10 USD
- Spot rate on payment date (2026-05-25): 1 EUR = 1.13 USD
- Month-end close (2026-05-31): open foreign liabilities revalued at closing rate

## Step 1: Initial Recognition (Invoice Date)

Record inventory expense and accounts payable at invoice-date spot rate.

- USD equivalent = 10,000 x 1.10 = USD 11,000

| Account | Debit (USD) | Credit (USD) | Control Rationale |
| --- | ---: | ---: | --- |
| Inventory / Expense | 11,000 | 0 | Recognize purchase at spot rate on transaction date. |
| Accounts Payable (EUR-denominated) | 0 | 11,000 | Liability captured in functional currency for reporting. |

Journal control checks:

- Debits equal credits (11,000 = 11,000).
- Source document reference (invoice id, vendor id) is attached.
- Transaction date and rate source are persisted.

## Step 2: Settlement (Payment Date)

Supplier is paid at a different FX rate.

- Cash paid in USD terms = 10,000 x 1.13 = USD 11,300
- Existing payable carrying amount = USD 11,000
- Realized FX loss = USD 300

| Account | Debit (USD) | Credit (USD) | Control Rationale |
| --- | ---: | ---: | --- |
| Accounts Payable | 11,000 | 0 | Remove original liability carrying value. |
| Realized FX Loss | 300 | 0 | Capture movement due to settlement rate difference. |
| Cash | 0 | 11,300 | Record cash outflow at actual conversion amount. |

Journal control checks:

- Debits equal credits (11,300 = 11,300).
- Realized gain/loss account is mandatory when settlement rate differs.
- Payment reference is linked to original invoice transaction.

## Step 3: Month-End Revaluation (If Liability Remains Open)

If payment has not occurred by period-end, revalue open EUR liabilities using
closing rate and book unrealized gain/loss.

Example assumptions for an open balance:

- Remaining payable: EUR 4,000
- Original carrying amount at 1.10: USD 4,400
- Closing rate at 1.12: USD 4,480
- Unrealized FX loss: USD 80

| Account | Debit (USD) | Credit (USD) | Control Rationale |
| --- | ---: | ---: | --- |
| Unrealized FX Loss | 80 | 0 | Recognize period-end valuation impact. |
| Accounts Payable | 0 | 80 | Adjust liability carrying amount to closing rate. |

Journal control checks:

- Revaluation postings are tagged as period-end adjustments.
- Revaluation reversals or roll-forward policy is documented.
- Closing rate source and timestamp are immutable audit fields.

## Minimal Validation Checklist

Use this checklist in release validation and accounting test suites:

- Every posting set balances to zero in functional currency.
- FX rate source is reproducible (provider, timestamp, base/quote pair).
- Realized vs unrealized FX impacts are separated into distinct accounts.
- Revaluation logic only applies to open foreign-currency balances.
- Journal entries preserve source references for traceability.
