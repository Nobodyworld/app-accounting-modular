# Tax Data Model

`TaxRule`:
- `jurisdiction`: e.g., `US-FED`, `US-CA`, `EU-IE`, `GLOBAL`
- `scope`: e.g., `corporate_income`, `vat`, `payroll`
- `expression`: a simple expression or JSON logic describing applicability and rate
- `valid_from`, `valid_to`

## Roadmap Enhancements
- Strong typing for expressions (e.g., JSONLogic schema enforced at validation time)
- Precedence & override strategy for overlapping jurisdictions
- Source provenance (URL, statute reference) stored alongside rules
- Automated updaters per jurisdiction to refresh rules from authoritative feeds
