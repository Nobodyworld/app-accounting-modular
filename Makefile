PYTHON ?= python
PIP ?= pip

.PHONY: install lint format typecheck test coverage quality security health audit

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

audit:
	$(PYTHON) -m tools.audit_metrics --format markdown --output REPORTS/audit-latest.md
