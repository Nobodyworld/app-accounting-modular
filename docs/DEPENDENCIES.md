# Dependency and Security Posture

This project maintains dependency compatibility for Python 3.12+ while using
Python 3.14 as the primary development baseline.

## Python Policy

- Minimum supported Python: 3.12
- Primary development Python: 3.14
- CI-enforced versions: 3.12, 3.13, 3.14

## Runtime Dependencies

Runtime dependencies are declared in `requirements.txt` using bounded ranges to
allow interpreter-compatible patch/minor upgrades without locking to a single
wheel build.

Key runtime groups:

- API/runtime: `fastapi`, `pydantic`, `sqlmodel`, `uvicorn`, `httpx`
- Accounting and data: `pandas`, `numpy`, `statsmodels`, `scikit-learn`
- Providers: `requests`, `yfinance`, `python-jose`, `python-dateutil`
- Operations/web: `APScheduler`, `streamlit`, `python-dotenv`

## Development Dependencies

Development dependencies are declared in `requirements-dev.txt` and include:

- Quality tooling: `ruff`, `black`, `mypy`
- Test tooling: `pytest`, `pytest-cov`
- Security tooling: `pip-audit`

## Security Audit Policy

- `safety` is deprecated in this repository and replaced by `pip-audit`.
- Dependency vulnerability scanning is scoped to repository-declared
  requirements via:

```bash
python -m pip_audit -r requirements.txt -r requirements-dev.txt
```

This avoids reporting unrelated global packages from reused environments.

## Release Validation

Release validation must include:

- dependency installation in a fresh virtual environment
- `python -m pip check`
- project-scoped `pip-audit` run
- quality gate execution (`python -m src.tools.quality_gate`)
