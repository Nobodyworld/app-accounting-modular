# Ruff 0.16 Migration Policy

This document records the deliberate migration from Ruff `0.15.21` to Ruff
`0.16.0`. Ruff is a development-only linter and formatter; this change does not
alter the runtime compatibility manifest or the generated container lock.

## Why the migration is isolated

Ruff `0.16.0` introduced two defaults that could otherwise create unrelated
repository churn:

- the default lint selection expanded substantially; and
- Python code fences in Markdown files became formatter inputs by default.

The repository does not inherit either behavior implicitly. Tool upgrades must
not silently change the reviewed lint policy or rewrite documentation while a
product or security branch is in progress.

## Adopted policy

The exact development pin is:

```text
ruff==0.16.0
```

`pyproject.toml` makes the repository contract explicit:

- discovered files are Python files, stub files, and `pyproject.toml`;
- Markdown and notebooks are excluded;
- exclusions remain effective even when a file is passed explicitly;
- lint families remain `E`, `F`, `I`, `UP`, and `B`;
- `B008` remains ignored for FastAPI dependency-injection defaults;
- lint and formatter preview modes remain disabled;
- docstring code formatting remains disabled; and
- source formatting remains double-quoted, space-indented, LF-terminated, and
  limited to 120 columns.

The normal commands remain:

```bash
python -m ruff check .
python -m ruff format --check .
```

Their target set is now controlled by explicit repository configuration rather
than Ruff release defaults.

## Markdown policy

Markdown Python fences are documentation content and are not part of the normal
Ruff gate. This preserves reviewable documentation diffs and prevents a tooling
upgrade from rewriting code examples throughout the repository.

A future documentation-formatting proposal may enable Ruff for selected
Markdown paths or add a separate command. That decision must be reviewed as its
own scope and must not be smuggled into routine dependency updates.

## Validation

`tests/test_ruff_migration_policy.py` verifies:

- the exact Ruff version and requirement pin;
- explicit rule selection and preview settings;
- explicit discovery and exclusion policy;
- unchanged quality-gate commands;
- a malformed Python fence in Markdown is ignored; and
- an equivalently malformed Python source file is still detected by the
  formatter.

The complete migration must also pass:

- Ruff lint and formatting;
- full pytest and coverage gates;
- all critical-module floors;
- the 52-test accounting-control subset;
- mypy;
- `pip check`;
- runtime and development dependency audits;
- current-tree and full-history secret scans;
- Python 3.12, 3.13, and 3.14 hosted jobs;
- changed-production coverage;
- container supply-chain validation; and
- required container smoke.

## Scope boundary

This migration does not add new lint families, enable preview rules, remove
Black, format Markdown, change application behavior, alter runtime dependencies,
regenerate `requirements-container.lock`, or approve broader deployment.
