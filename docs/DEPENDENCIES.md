# Dependency and Security Posture

This project maintains dependency compatibility for Python 3.12+ while using
Python 3.14 as the primary development baseline.

## Python Policy

- Minimum supported Python: 3.12
- Primary development Python: 3.14
- CI workflow matrix: 3.12, 3.13, 3.14

## Runtime Dependencies

Runtime dependencies are declared in `requirements.txt` using bounded ranges to
allow interpreter-compatible patch/minor upgrades without locking to a single
wheel build. This human-reviewed compatibility manifest remains the sole input
for container dependency resolution; its ranges are not replaced by manually
maintained exact pins.

Key runtime groups:

- API/runtime: `fastapi`, `pydantic`, `sqlmodel`, `uvicorn`, `httpx`
- Accounting and data: `pandas`, `numpy`, `statsmodels`, `scikit-learn`
- Providers: `requests`, `yfinance`, `python-jose`, `python-dateutil`
- Operations/web: `APScheduler`, `streamlit`, `python-dotenv`

`requests` provider calls are centralized behind the outbound response boundary
documented in [`PLUGINS.md`](PLUGINS.md). The `yfinance` dependency exposes a
high-level download API that returns a fully materialized DataFrame. The
application therefore constrains requested range, timeout, threading, call
count, and returned rows, but cannot independently stream or byte-count
YFinance's internal HTTP body. Dependency audit success alone does not
establish container reproducibility or attestation. The separate generated and
verified artifacts below provide that evidence.

### Generated container lock

`requirements-container.lock` is the committed Python 3.14/Linux runtime
artifact generated from `requirements.txt`. It contains the complete dependency
graph as exact versions with hashes, including the `uvicorn[standard]` and
`PyJWT[crypto]` extras. Its header binds it to the input fingerprint, generator,
Python/platform policy, and digest-pinned base image. The current lock contains
19 direct and 65 transitive requirements and has SHA-256
`990aa39c04686870f6907074b32d01eff81f69f84f9281d98aefa91fb72163d9`.

`requirements-lock-tools.lock` separately pins and hashes `uv==0.12.0`. Its
SHA-256 is
`2522c140fe61233b873b30a8cb54e613e80f2c4bea1ea39f64e21f37b2a4d51a`.
The generator runs only inside the pinned container and is not installed in
application images. See the
[container supply-chain guide](container-supply-chain.md) for bootstrap,
regeneration, and review procedures.

Normal validation is offline:

```bash
python scripts/dependencies/verify_container_lock.py
```

The verifier compares the canonical-LF `requirements.txt` fingerprint, checks
the lock metadata and policy, and rejects non-exact, unhashed, duplicate,
editable, VCS, or direct-URL entries. It does not re-resolve PyPI, so a new
package release cannot break an unrelated pull request. Dependency refreshes
are deliberate operations using the documented Docker-backed generator.

## Development Dependencies

Development dependencies are declared in `requirements-dev.txt` and include:

- Quality tooling: `ruff`, `black`, `mypy`
- Test tooling: `pytest`, `pytest-cov`
- Security tooling: `pip-audit`

Most human-edited development dependencies retain bounded compatibility ranges.
`ruff==0.15.21` is intentionally exact because formatter and linter output must
stay stable, quality-gate behavior must be reproducible, and formatting changes
should receive deliberate review. This development-tool pin is independent of,
and is not a substitute for, the runtime container lock.

## Security Audit Policy

- `safety` is deprecated in this repository and replaced by `pip-audit`.
- Dependency vulnerability scanning is scoped to repository-declared
  requirements via:

```bash
python -m pip_audit -r requirements.txt -r requirements-dev.txt
```

This avoids reporting unrelated global packages from reused environments.
The exact runtime container graph is audited separately after regeneration and
in the quality workflow:

```bash
python -m pip_audit --require-hashes --disable-pip -r requirements-container.lock
```

No image vulnerability scan is currently included. Available vulnerability
databases can change independently of the source commit, and no pinned scanner
with a reviewably deterministic database was established for this tranche.
This limitation does not weaken the runtime-lock `pip-audit` requirement.

Dependency auditing does not replace full-history secret scanning. Public release
validation also requires a Gitleaks or equivalent scan across Git history, with
tool version, command, commits scanned, findings, false-positive disposition, and
final result recorded in [`../PUBLIC_RELEASE_AUDIT.md`](../PUBLIC_RELEASE_AUDIT.md).

## Release Validation

Release validation must include:

- dependency installation in a fresh virtual environment
- `python -m pip check`
- offline container-lock verification
- `pip-audit` against `requirements-container.lock`
- project-scoped `pip-audit` run
- container image inventories, SPDX SBOMs, and SHA-256 evidence
- quality gate execution (`python -m src.tools.quality_gate`)
- full-history secret scan evidence
- clean-clone validation of the final publication commit
