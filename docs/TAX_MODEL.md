# Tax Data Model

This document describes the tax rule data model and how tax calculations are performed in Modular Accounting.

## TaxRule Structure

The `TaxRule` class represents a tax rule with the following attributes:

- `jurisdiction`: String identifier for the tax jurisdiction (e.g., `US-FED`, `US-CA`, `EU-IE`, `GLOBAL`)
- `scope`: Tax type or category (e.g., `corporate_income`, `vat`, `payroll`, `sales_tax`)
- `expression`: Tax calculation expression or rate
- `description`: Human-readable description of the rule
- `effective_from`: Date when the rule becomes effective
- `effective_to`: Optional date when the rule expires
- `metadata`: Additional structured data about the rule

## Tax Calculation

Tax rules are applied based on:

1. **Jurisdiction matching**: Rules are filtered by the specified jurisdiction
2. **Scope matching**: Rules are filtered by tax type
3. **Date validity**: Only rules effective for the transaction date are considered
4. **Expression evaluation**: Tax amounts are calculated using the rule's expression

## Expression Format

Tax expressions can be:

- **Simple rates**: Decimal values (e.g., `0.21` for 21% VAT)
- **Complex expressions**: JSON logic for conditional rates or tiered taxation
- **References**: Links to external tax tables or calculation engines

## Examples

### Simple VAT Rule
```python
TaxRule(
    jurisdiction="EU",
    scope="vat",
    expression=Decimal("0.21"),
    description="EU Standard VAT Rate",
    effective_from=date(2024, 1, 1)
)
```

### Complex Corporate Tax Rule
```python
TaxRule(
    jurisdiction="US-FED",
    scope="corporate_income",
    expression={
        "type": "tiered",
        "brackets": [
            {"min": 0, "max": 100000, "rate": 0.15},
            {"min": 100000, "max": 500000, "rate": 0.25},
            {"min": 500000, "rate": 0.35}
        ]
    },
    description="US Federal Corporate Income Tax",
    effective_from=date(2024, 1, 1)
)
```

## Tax Providers

Tax rules are loaded through `TaxDataPort` implementations:

- **OECD Stub**: Basic international tax rules
- **Custom Providers**: Implement `get_rules(jurisdiction: str | None)` to provide jurisdiction-specific rules

## Future Enhancements

- Expression type system for safer calculations
- Rule precedence and conflict resolution
- Automated jurisdictional updates
- Tax rule provenance and audit trails

See TASKLIST.md for detailed tracking of tax model improvements.
