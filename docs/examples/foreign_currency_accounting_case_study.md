# Foreign Currency Accounting Case Study

This end-to-end case demonstrates a complete multi-currency payable workflow:

- foreign-currency invoice recognition
- month-end remeasurement
- balanced journal output at each step
- provider and rate provenance retained for auditability

## Demonstration Boundary

This case study is an accounting-control demonstration for a single foreign-currency payable lifecycle.

- It demonstrates journal balancing, valuation mechanics, and rate provenance.
- It does not represent a full ERP, production tax engine, treasury platform, or complete general-ledger implementation.
- It uses simplified, controlled inputs so calculations are transparent for audit review.

## Supported Controls Demonstrated

- Balanced journal-entry validation at each posting step.
- Account traceability through explicit account codes and transaction IDs.
- Initial recognition at transaction-date spot rate.
- Period-end remeasurement for open foreign-currency liabilities.
- Settlement against carrying value with realized FX separation.
- Provenance capture for provider key, pair, timestamp, and rate source detail.

## Assumptions and Simplifications

- Single payable, single reporting currency (USD), and deterministic sample rates.
- No discounting, hedge accounting, or transaction-cost adjustments.
- Tax treatment is out of scope for this FX journal-only demonstration.
- Numbers are intentionally compact and rounded for explainability.

## Scenario

- Functional/presentation currency: USD
- Supplier invoice currency: EUR
- Invoice principal: EUR 10,000
- Invoice date: 2026-05-10 (spot 1 EUR = 1.10 USD)
- Month-end close date: 2026-05-31 (closing 1 EUR = 1.12 USD)
- Settlement date: 2026-06-15 (spot 1 EUR = 1.13 USD)

## Provider and Rate Provenance

The journal package stores a provenance block per valuation event so each
posting can be traced back to immutable market inputs.

| Event | Pair | Rate | As Of (UTC) | Provider Key | Provider Detail |
| --- | --- | ---: | --- | --- | --- |
| Invoice recognition | EUR/USD | 1.10 | 2026-05-10T10:00:00Z | fx_openexchangerates | OpenExchangeRates daily close |
| Month-end remeasurement | EUR/USD | 1.12 | 2026-05-31T23:00:00Z | fx_openexchangerates | OpenExchangeRates month-end close |
| Settlement | EUR/USD | 1.13 | 2026-06-15T09:00:00Z | fx_openexchangerates | OpenExchangeRates settlement-day quote |

Example provenance envelope persisted with the case-study output:

```json
{
 "providers": {
  "fx": "fx_openexchangerates",
  "tax": "tax_us",
  "commodities": "market_commodities"
 },
 "fx_rate_evidence": [
  {
   "event": "invoice_recognition",
   "pair": "EUR/USD",
   "rate": "1.10",
   "as_of": "2026-05-10T10:00:00Z",
   "source": "OpenExchangeRates daily close"
  },
  {
   "event": "month_end_remeasurement",
   "pair": "EUR/USD",
   "rate": "1.12",
   "as_of": "2026-05-31T23:00:00Z",
   "source": "OpenExchangeRates month-end close"
  },
  {
   "event": "settlement",
   "pair": "EUR/USD",
   "rate": "1.13",
   "as_of": "2026-06-15T09:00:00Z",
   "source": "OpenExchangeRates settlement-day quote"
  }
 ]
}
```

## Step 1: Invoice Recognition

- EUR 10,000 x 1.10 = USD 11,000

| Account | Debit (USD) | Credit (USD) | Control Rationale |
| --- | ---: | ---: | --- |
| Inventory / Expense | 11,000 | 0 | Recognize supplier invoice at transaction-date spot rate. |
| Accounts Payable (EUR) | 0 | 11,000 | Carry EUR liability in functional currency for reporting. |

Balance check: 11,000 debit = 11,000 credit.

## Step 2: Month-End Remeasurement (Liability Still Open)

- Carrying value before remeasurement: EUR 10,000 x 1.10 = USD 11,000
- Closing carrying value at period end: EUR 10,000 x 1.12 = USD 11,200
- Unrealized FX loss: USD 200

| Account | Debit (USD) | Credit (USD) | Control Rationale |
| --- | ---: | ---: | --- |
| Unrealized FX Loss | 200 | 0 | Recognize valuation movement for open foreign-currency liability. |
| Accounts Payable (EUR) | 0 | 200 | Remeasure payable to month-end carrying amount. |

Balance check: 200 debit = 200 credit.

## Step 3: Settlement After Remeasurement

- Payable carrying value after month-end close: USD 11,200
- Cash paid on settlement date: EUR 10,000 x 1.13 = USD 11,300
- Realized FX loss at settlement: USD 100

| Account | Debit (USD) | Credit (USD) | Control Rationale |
| --- | ---: | ---: | --- |
| Accounts Payable (EUR) | 11,200 | 0 | Derecognize remeasured liability at latest carrying value. |
| Realized FX Loss | 100 | 0 | Recognize settlement-date delta against carrying amount. |
| Cash | 0 | 11,300 | Record actual functional-currency cash outflow. |

Balance check: 11,300 debit = 11,300 credit.

## Optional Subsequent-Close Pattern

When an organization posts an automated month-end remeasurement reversal at the next period open, settlement still resolves to the same economic result: the payable is derecognized at current carrying value and any residual is recognized as realized FX gain/loss. This repository demonstrates the core carrying-value settlement control; reversal policy remains implementation-specific.

## Balanced Journal Output (Terminal Evidence)

```text
TXN AP-INV-2026-05-10
 debits:  11,000.00 USD
 credits: 11,000.00 USD
 balanced: true

TXN AP-RM-2026-05-31
 debits:  200.00 USD
 credits: 200.00 USD
 balanced: true

TXN AP-PMT-2026-06-15
 debits:  11,300.00 USD
 credits: 11,300.00 USD
 balanced: true
```

Rendered terminal-output image:

![Terminal evidence for balanced journal output](assets/fx-case-study-terminal.svg)

Rendered journal-summary image:

![Journal summary with realized and unrealized FX split](assets/fx-case-study-journal.svg)

## Outcome Summary

- Total FX loss recognized: USD 300
- Composition of loss:
  - Unrealized at month-end: USD 200
  - Realized at settlement: USD 100
- Net accounting integrity:
  - all posting sets are balanced
  - realized and unrealized effects are separated
  - every valuation event is linked to provider and rate provenance

## Validation Checklist

- Every transaction passes the journal balancing rule (`Transaction.is_balanced()`).
- Provider key, pair, timestamp, and rate are retained for each valuation event.
- Month-end remeasurement is applied only while the payable remains open.
- Settlement removes the payable at carrying value and books only the residual
 realized difference.
- Source references (invoice id, vendor id, payment id, close run id) are
 persisted with each posting package.
