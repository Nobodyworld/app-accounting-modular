# Tax Data Model

`TaxRule`:
- `jurisdiction`: e.g., `US-FED`, `US-CA`, `EU-IE`, `GLOBAL`
- `scope`: e.g., `corporate_income`, `vat`, `payroll`
- `expression`: a simple expression or JSON logic describing applicability and rate
- `valid_from`, `valid_to`

# TODO
- Add strong typing for expressions (e.g., JSONLogic schema)
- Add precedence & override strategy
- Add source provenance (URL, statute reference)
- Add automated updaters per jurisdiction
