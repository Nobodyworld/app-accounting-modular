PYTHON ?= python
PIP ?= pip

.PHONY: install lint format typecheck test coverage quality security health plan-validate quality-gate audit release

install:
	$(PIP) install -r requirements-dev.txt

lint:
	ruff check .

format:
	ruff format .

typecheck:
	mypy apps/modular_accounting/application apps/api apps/extensions cli tests

test:
	pytest --cov=apps --cov=plugins --cov=cli --cov-report=term-missing --cov-fail-under=85

coverage: test

security:
	$(PYTHON) -m pip install --quiet safety==3.2.1 && safety check --full-report

quality: lint typecheck test security

ci: lint typecheck test security

health:
	$(PYTHON) -m cli.macli health

quality-gate:
	$(PYTHON) -m tools.quality_gate

plan-validate:
	test -n "$(PLAN)" || (echo "PLAN=<path> is required" >&2 && exit 1)
	$(PYTHON) -m cli.macli inspect-plan --plan $(PLAN)

audit:
	$(PYTHON) -m tools.audit_metrics --format markdown --output docs/reports/audit-latest.md

release:
	$(PYTHON) -m tools.release_manager bump --part $${PART:-patch} --message "$${MESSAGE:-TODO: describe release}"
