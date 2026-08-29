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
- Providers: `requests`, `yfinance`, `PyJWT`, `python-dateutil`
- Operations/web: `APScheduler`, `streamlit`, `python-dotenv`

The reviewed minimums currently require `PyJWT[crypto]>=2.13.0,<3.0` and
`streamlit>=1.61.1,<2.0`. PyJWT 2.13.0 supplies the adopted token and JWK
hardening boundary. Streamlit 1.61.1 is the tested minimum for the current
accountant-facing workspace and repository-root-safe AppTest behavior.

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
19 direct and 57 transitive requirements and has SHA-256
`5b110e5a7926b5248d6182af035dda9296f1fbfd73133b2dc88059c5f26f56ed`.
The canonical-LF `requirements.txt` input fingerprint is
`c748d7807e46f9cf5f8348e05c9a4886f5130fba6e21da7829bbc03b61d878dc`.

The August 2026 consolidated refresh moved Streamlit from 1.60.0 to 1.61.1 and
kept PyJWT at the already locked 2.13.0 while raising its supported minimum.
The same deterministic resolution advanced `cffi`, `curl-cffi`, `greenlet`,
`numpy`, `packaging`, `platformdirs`, `soupsieve`, `SQLAlchemy`,
`typing-inspection`, and `uvicorn`. Streamlit's new graph removed the runtime
`GitPython`, `gitdb`, `smmap`, `markdown-it-py`, `mdurl`, `Pygments`, and `rich`
packages. These are generated transitive outcomes, not hand-edited lock
choices.

The 2026-08-12 v0.2 maintenance closeout widened the reviewed YFinance range to
`yfinance>=0.2.44,<2.0` and generated `yfinance==1.5.2`. The installed download
signature retains the provider's bounded `timeout` and `multi_level_index`
options; offline contracts also cover a `None` result and prevent private
upstream exception text from entering application logs. The generated graph
retained `curl-cffi==0.16.0`, removed `frozendict`, and advanced
`charset-normalizer` from 3.4.9 to 3.5.0 and `typing-inspection` from 0.4.3 to
0.4.4 as reviewed transitive patch outcomes. No other package version moved.

`requirements-lock-tools.lock` separately pins and hashes `uv==0.12.0`. Its
SHA-256 is
`aff84fdd6d16ce2a4ea44c059f2f4c47bb0760acce5c585981b2f1e31317a8dd`.
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

### Dependabot policy

Pip updates use `versioning-strategy: increase-if-necessary`. Dependabot should
therefore preserve a compatible manifest floor when the existing range already
permits a newer release. Any change to `requirements.txt` that does alter the
reviewed compatibility boundary must still regenerate and review the complete
hashed container lock before merge. A manifest-only dependency PR is expected
to fail the lock fingerprint check; that failure must not be bypassed.

## Development Dependencies

Development dependencies are declared in `requirements-dev.txt` and include:

- Quality tooling: `ruff`, `black`, `mypy`
- Test and package tooling: `pytest`, `pytest-cov`, and the exact `build==1.3.0`
  standard PEP 517 frontend used by Provider Author Kit acceptance
- Security tooling: `pip-audit`

Most human-edited development dependencies retain bounded compatibility ranges.
`ruff==0.16.2` is intentionally exact because formatter and linter output must
stay stable, quality-gate behavior must be reproducible, and formatting changes
should receive deliberate review. The reviewed patch from the original 0.16.0
migration did not change lint selection, discovery, preview, or formatting
policy. Ordinary Ruff commands evaluate Python/stub files and `pyproject.toml`,
while Markdown and notebooks remain outside the Ruff format gate. See the
[Ruff 0.16 migration policy](quality/ruff-0.16-migration.md). This
development-tool pin is independent of, and is not a substitute for, the
runtime container lock.

## GitHub Actions dependencies

All executable action references remain pinned to full commit SHAs. The
attestation workflow uses `actions/attest` v4.2.2 at
`1e69f48acb82d1966a394da916b4c1698aa569d6`. Attestation write permissions
remain isolated to the trusted `main` event job; pull-request runs build and
upload ordinary evidence but do not publish attestations.

## Security Audit Policy

- `safety` is deprecated in this repository and replaced by `pip-audit`.
- Dependency vulnerability scanning is scoped to repository-declared
  requirements via:

```bash
python -m pip_audit -r requirements-dev.txt
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
