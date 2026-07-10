PYTHON ?= python
PIP ?= pip

.PHONY: install lint format format-check typecheck test coverage quality security health plan-validate quality-gate audit release ci

install:
	$(PIP) install -r requirements-dev.txt

lint:
	ruff check .

format:
	ruff format .

format-check:
	ruff format --check .

typecheck:
	mypy src/apps/modular_accounting/application src/apps/api src/apps/extensions src/cli tests

test:
	pytest --cov=src/apps --cov=src/plugins --cov=src/cli --cov-report=term-missing --cov-fail-under=85

coverage: test

security:
	$(PYTHON) -m pip_audit --timeout 60 -r requirements.txt -r requirements-dev.txt

quality: lint format-check typecheck test security

ci: lint format-check typecheck test security

health:
	$(PYTHON) -m cli.macli health

quality-gate:
	$(PYTHON) -m src.tools.quality_gate

plan-validate:
	test -n "$(PLAN)" || (echo "PLAN=<path> is required" >&2 && exit 1)
	$(PYTHON) -m cli.macli inspect-plan --plan $(PLAN)

audit:
	$(PYTHON) -m tools.audit_metrics --format markdown --output docs/reports/audit-latest.md

release:
	$(PYTHON) -m tools.release_manager bump --part $${PART:-patch} --message "$${MESSAGE:-TODO: describe release}"
