# Setup

## Local Provider Author Kit

The application source checkout needs both source roots:

```powershell
$env:PYTHONPATH = "$PWD\src;$PWD\packages\provider-sdk\src"
```

The SDK itself has zero runtime dependencies. Build or accept only local
artifacts for this Early Beta demonstration; the repository acceptance harness
creates clean author/consumer environments, sets `PIP_NO_INDEX=1`, builds
through the declared PEP 517 backends, installs wheel and sdist variants from
local artifacts only, and cleans all disposable state:

```console
python scripts/provider_author_acceptance.py --output provider-author-acceptance.json
```

Do not publish the package or treat installation as application authorization.

The standard local SDK build is network-free because its declared backend has
no build requirements:

```console
PIP_NO_INDEX=1 python -m build --no-isolation packages/provider-sdk
```

This guide covers the validated local-development and container workflows for Modular Accounting.

## Prerequisites

- Python 3.12, 3.13, or 3.14
- `pip`
- Git
- Optional: GNU Make
- Optional: Docker with the `docker compose` and Buildx plugins
- Optional: GitHub CLI for verifying trusted-run attestations

The hosted CI matrix validates Python 3.12, 3.13, and 3.14. Python 3.14 is the primary development target.

## Local Installation

From the repository root:

```bash
git clone https://github.com/Nobodyworld/app-accounting-modular.git
cd app-accounting-modular
python -m venv .venv
```

Activate the environment.

### Windows PowerShell

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
$env:PYTHONPATH = "$PWD\src;$PWD\packages\provider-sdk\src"
```

### macOS or Linux

```bash
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
export PYTHONPATH="$PWD/src:$PWD/packages/provider-sdk/src${PYTHONPATH:+:$PYTHONPATH}"
```

`make install` is an equivalent convenience target on systems with GNU Make.

## Configuration

The application runs locally with SQLite and controlled demonstration providers by default. For persistent sessions or external providers, configure environment variables before startup.

The documented example is [`../config/.env.example`](../config/.env.example). To load a dotenv file explicitly:

### Windows PowerShell

```powershell
Copy-Item config/.env.example .env
$env:MODACCT_ENV_FILE = "$PWD\.env"
```

### macOS or Linux

```bash
cp config/.env.example .env
export MODACCT_ENV_FILE="$PWD/.env"
```

The example intentionally leaves `MODACCT_JWT_SECRET_KEY` empty. Generate and store a stable high-entropy value before using persistent authentication sessions or Docker Compose. Never commit the generated value.

Common variables:

```text
MODACCT_DATABASE_URL=sqlite:///./modacct.db
MODACCT_JWT_SECRET_KEY=
MODACCT_JWT_ALGORITHM=HS256
MODACCT_ACCESS_TOKEN_EXPIRE_MINUTES=60
MODACCT_MAX_REQUEST_BODY_BYTES=2097152
MODACCT_LOG_LEVEL=INFO
MODACCT_LOG_FORMAT=JSON
MODACCT_OPENEX_APP_ID=
MODACCT_ALPHAVANTAGE_KEY=
MODACCT_NEWSAPI_KEY=
MODACCT_GDELT_USER_AGENT=
```

Provider and extension catalogs are currently defined in `src/apps/api/config.py`; nested `MODACCT_ALLOWED_PROVIDERS__...` environment keys are not a supported configuration interface.

`MODACCT_MAX_REQUEST_BODY_BYTES` defaults to 2 MiB and may only be lowered.
See the [application resource-limits guide](resource-limits.md) for schema,
metadata, upload, response-contract, and reverse-proxy requirements.

## Run the Application

### API

```bash
python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

- API: `http://127.0.0.1:8000`
- OpenAPI: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health`

Use `--reload` only for local development.

### Streamlit demonstration

In another activated shell with `PYTHONPATH` configured:

```bash
streamlit run src/apps/web/app.py
```

The interface is available at `http://127.0.0.1:8501` and expects the API at `http://localhost:8000` unless `API_BASE` is overridden.

Budget CSV and scenario-plan uploads have a 1 MiB application limit.
`.streamlit/config.toml` also configures Streamlit's framework cap at 2 decimal
megabytes as defense in depth; the application check remains authoritative.

Snapshot Review is a public/local evidence workflow. Its provider controls come
from conforming providers in current process configuration and snapshot
generation stays in the local `SnapshotOrchestrator`; it does not query tenant
policy or defaults. Provider Governance, Scenario Plan Review, and Review
Utilities require an authenticated API session and a positive organization ID.
Uploading a scenario-plan file remains local input, while requesting its
rendered preview uses the protected FastAPI boundary.

The retained primary repository screenshot represents the public Snapshot
Review flow; it does not depict the authenticated Scenario Plan Review or
Review Utilities panels.

### CLI

```bash
python -m cli.macli snapshot --base USD --commodity XAU --jurisdiction US --format table
python -m cli.macli inspect-plan --plan docs/examples/scenario-plan.json
python -m cli.macli snapshot-scenarios --plan docs/examples/scenario-plan.json --format table
python -m cli.macli health
python -m cli.macli observe
python -m cli.macli inspect-extensions
python -m cli.macli inspect-contracts
python -m cli.macli provider-sdk governance-reconcile --format table
python -m cli.macli provider-sdk governance-validate --format table
python -m cli.macli provider-sdk governance-export --organization-id 1 --format json
```

Provider governance reconciliation is structural and network-free. `settings.allowed_providers` remains the only executable trust source. The first reconcile records safe metadata; later identity drift is quarantined and requires explicit operator review before `--accept-drift`. Organization administrators manage only already-trusted keys through the authenticated API or Streamlit workspace. Credential readiness reports manifest-declared environment-variable names and booleans, never their values.

## Docker Compose

Docker Compose requires an explicit JWT signing secret and fails before startup when `MODACCT_JWT_SECRET_KEY` is missing or empty.

Generate a temporary high-entropy secret for the current shell.

### Windows PowerShell

```powershell
$env:MODACCT_JWT_SECRET_KEY = (python -c "import secrets; print(secrets.token_urlsafe(48))")
docker compose -f config/docker-compose.yml up --build
```

### macOS or Linux

```bash
export MODACCT_JWT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
docker compose -f config/docker-compose.yml up --build
```

For stable sessions across restarts, store a generated secret in a local, ignored `.env` file instead of regenerating it. Do not use the empty example value and do not commit the generated secret.

The default Compose configuration:

- builds both images from the repository root;
- runs both application processes as numeric UID/GID `10001:10001`;
- sets `/app/src` and `/app/packages/provider-sdk/src` on `PYTHONPATH`;
- gives the API a persistent SQLite volume mounted at `/data`;
- uses read-only root filesystems for both services;
- drops all Linux capabilities and enables `no-new-privileges`;
- provides a bounded writable `/tmp` tmpfs to each service;
- points Streamlit to `http://api:8000`;
- waits for API health before starting the web service; and
- publishes host ports explicitly on `127.0.0.1` only.

The API may write to `/data` and `/tmp`. The web service may write only to `/tmp`. Application source under `/app` remains read-only at runtime.

The application processes listen on the container network so the services can communicate, but the host port mappings remain loopback-only by default.

Endpoints:

- API: `http://127.0.0.1:8000`
- OpenAPI: `http://127.0.0.1:8000/docs`
- Streamlit: `http://127.0.0.1:8501`

This Compose profile is validated only for local demonstration. Do not change the host bindings to `0.0.0.0`, a LAN address, or a public interface without a separate deployment review covering HTTPS termination, trusted proxies/hosts, network access controls, secret management, and host/container security controls.

Any reverse proxy or ingress placed in front of the API must enforce a request
body limit equal to or smaller than the configured application limit.

Stop and remove the services:

```bash
docker compose -f config/docker-compose.yml down
```

Remove the demonstration database volume as well:

```bash
docker compose -f config/docker-compose.yml down -v
```

Individual image builds from the repository root:

```bash
docker build -f config/Dockerfile.api -t modacct-api .
docker build -f config/Dockerfile.web -t modacct-web .
```

### Container dependency workflow

The API and web Dockerfiles share the official digest-pinned
`python:3.14-slim` base and install only the exact, hashed graph in
`requirements-container.lock`. The `requirements.txt` and
`requirements-dev.txt` files remain human-reviewed compatibility manifests.
The local-development commands above may update pip in a developer virtual
environment; application container builds do not update the pip supplied by
their pinned base.

Regenerate the runtime lock only for an intentional dependency or base-image
update. Docker Desktop users can run:

```powershell
pwsh scripts/dependencies/Generate-ContainerLock.ps1
```

On Linux:

```bash
sh scripts/dependencies/generate-container-lock.sh
```

Freshness and structural policy checks are offline and never rewrite the lock:

```bash
python scripts/dependencies/verify_container_lock.py
pytest -q tests/test_container_supply_chain.py
```

For clean dependency-resolution evidence, build without the Docker cache:

```bash
docker build --no-cache -f config/Dockerfile.api -t modacct-api:repro .
docker build --no-cache -f config/Dockerfile.web -t modacct-web:repro .
```

Trusted workflow runs attach provenance and SPDX SBOM attestations to exported
image archives. After downloading an archive and its checksum, verify both:

```powershell
$SourceSha = "<source-commit-sha>"
$Archive = ".\container-evidence\modacct-api-$SourceSha.tar"
$Expected = (Select-String -Path ".\container-evidence\image-archives.sha256" -Pattern "modacct-api-$SourceSha\.tar$").Line.Split()[0]
$Actual = (Get-FileHash -Algorithm SHA256 $Archive).Hash.ToLowerInvariant()
if ($Actual -ne $Expected) { throw "API archive checksum mismatch" }
gh attestation verify $Archive --repo Nobodyworld/app-accounting-modular
```

Pull-request runs create ordinary checksum and SBOM evidence but intentionally
do not publish attestations. See the
[container supply-chain guide](container-supply-chain.md) for the exact base
digest, generator bootstrap, evidence inventory, update flow, and limitations.

The final images declare user `10001:10001`. Running them directly as root bypasses part of the validated Compose security boundary and is not the supported default.

## Validation

### Consolidated release gate

```bash
python -m src.tools.quality_gate
```

This runs Ruff, formatting validation, mypy, pytest with aggregate coverage enforcement, focused accounting-control suites, dependency checks, vulnerability auditing, and current-tree secret scanning.

### Make targets

```bash
make install
make lint
make format
make format-check
make typecheck
make test
make security
make quality
make quality-gate
make health
```

`make format` uses Ruff formatting. The repository does not use a `make type` target.

### Direct checks

```bash
python -m pip check
python -c "import apps.api.main, cli.macli, apps.modular_accounting.application; print('imports-ok')"
python tools/link_validator.py
python -m src.tools.secret_scan
```

## Troubleshooting

### `ModuleNotFoundError: No module named 'apps'`

The application and standalone SDK both use `src` layouts. Confirm that the virtual environment is active and `PYTHONPATH` contains both source roots.

Windows PowerShell:

```powershell
$env:PYTHONPATH = "$PWD\src;$PWD\packages\provider-sdk\src"
```

macOS or Linux:

```bash
export PYTHONPATH="$PWD/src:$PWD/packages/provider-sdk/src${PYTHONPATH:+:$PYTHONPATH}"
```

### Compose reports that `MODACCT_JWT_SECRET_KEY` is required

Generate a high-entropy value as shown in the Docker Compose section or set a stable generated value in a local ignored `.env` file. The repository intentionally does not ship a fallback signing key.

### API starts with an ephemeral JWT warning

Set a stable `MODACCT_JWT_SECRET_KEY` with at least 32 characters. The generated fallback is suitable only for temporary non-container local demonstrations and rotates on restart.

### Container reports a permission or read-only filesystem error

- API database files must be written under `/data`.
- Temporary files must be written under `/tmp`.
- Application files under `/app` are intentionally read-only.
- Do not change the services to root to bypass a path error; identify and document the required writable path instead.
- If an existing named volume was created with incompatible ownership, remove the demonstration volume with `docker compose -f config/docker-compose.yml down -v` and recreate it after confirming no data must be preserved.

### Database errors

- Confirm `MODACCT_DATABASE_URL` is a valid SQLAlchemy DSN.
- For SQLite, verify the target directory is writable.
- For PostgreSQL, verify connectivity and credentials.

### Provider failures

- Confirm the selected provider is present in the provider catalog.
- Confirm required external credentials are set.
- Use demo providers when reviewing the repository without third-party credentials.
- Inspect `/providers`, `/health`, and logs for the provider key and failure reason.

### Port conflicts

Change the local port passed to Uvicorn or Streamlit. For containers, change only the host-side port number while preserving the explicit `127.0.0.1` bind unless a separate deployment security review authorizes broader exposure.

## Scope Reminder

The default data and workflows are designed for demonstration and portfolio review. They are not production tax, treasury, bank-feed, or financial-reporting controls.
