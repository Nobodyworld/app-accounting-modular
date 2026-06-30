# docs/examples/

Sample plans and payloads referenced by CLI demos and automated tests.

- `scenario-plan.json` – Multi-scenario batch input for `cli.macli` commands.
- `ledger_persistence.md` – Examples of mapping domain transactions into external ledgers (QuickBooks, Xero, SQL).
- `foreign_currency_accounting_case_study.md` – End-to-end accounting control walkthrough for invoice, settlement, and revaluation in mixed currencies.
- `assets/fx-case-study-terminal.svg` – Terminal-style evidence image showing balanced journal output checks.
- `assets/fx-case-study-journal.svg` – Journal summary image highlighting realized/unrealized FX split.

These artifacts complement the walkthroughs in [docs/examples.md](../examples.md).

## Regenerating Visual Evidence

The image artifacts in `assets/` are committed documentation evidence, not
runtime outputs. When accounting assumptions change, regenerate both files by
updating their SVG text blocks so they match:

- journal amounts and balance checks in
 `foreign_currency_accounting_case_study.md`
- provider/rate provenance values shown in the case-study tables

Keep filenames stable (`fx-case-study-terminal.svg` and
`fx-case-study-journal.svg`) so existing README links remain valid.
