# Tax Data Model

`TaxRule`:

- `jurisdiction`: e.g., `US-FED`, `US-CA`, `EU-IE`, `GLOBAL`
- `scope`: e.g., `corporate_income`, `vat`, `payroll`
- `expression`: a simple expression or JSON logic describing applicability and rate
- `valid_from`, `valid_to`

## Follow-up Work

Outstanding enhancements for the tax model are tracked in TASKSLIST.md as TASK-0007 through TASK-0010, covering expression typing, precedence rules, provenance metadata, and automated jurisdictional updaters.
