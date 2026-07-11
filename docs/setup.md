# Setup

This guide covers the validated local-development and container workflows for Modular Accounting.

## Prerequisites

- Python 3.12, 3.13, or 3.14
- `pip`
- Git
- Optional: GNU Make
- Optional: Docker with the `docker compose` plugin

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
$env:PYTHONPATH = "$PWD\src"
```

### macOS or Linux

```bash
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
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

Replace every example credential value. At minimum, use a stable high-entropy `MODACCT_JWT_SECRET_KEY` for persistent authentication sessions.

Common variables:

```text
MODACCT_DATABASE_URL=sqlite:///./modacct.db
MODACCT_JWT_SECRET_KEY=replace-with-a-stable-32-plus-character-secret
MODACCT_JWT_ALGORITHM=HS256
MODACCT_ACCESS_TOKEN_EXPIRE_MINUTES=60
MODACCT_LOG_LEVEL=INFO
MODACCT_LOG_FORMAT=JSON
MODACCT_OPENEX_APP_ID=
MODACCT_ALPHAVANTAGE_KEY=
MODACCT_NEWSAPI_KEY=
MODACCT_GDELT_USER_AGENT=
```

Provider and extension catalogs are currently defined in `src/apps/api/config.py`; nested `MODACCT_ALLOWED_PROVIDERS__...` environment keys are not a supported configuration interface.

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

### CLI

```bash
python -m cli.macli snapshot --base USD --commodity XAU --jurisdiction US --format table
python -m cli.macli inspect-plan --plan docs/examples/scenario-plan.json
python -m cli.macli snapshot-scenarios --plan docs/examples/scenario-plan.json --format table
python -m cli.macli health
python -m cli.macli observe
python -m cli.macli inspect-extensions
python -m cli.macli inspect-contracts
```

## Docker Compose

Run Compose from the repository root and explicitly select the file under `config/`:

```bash
docker compose -f config/docker-compose.yml up --build
```

The Compose configuration:

- builds both images from the repository root;
- sets `/app/src` on `PYTHONPATH`;
- gives the API a persistent SQLite volume;
- points Streamlit to `http://api:8000`; and
- waits for API health before starting the web service.

Endpoints:

- API: `http://127.0.0.1:8000`
- OpenAPI: `http://127.0.0.1:8000/docs`
- Streamlit: `http://127.0.0.1:8501`

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

The repository uses a `src` layout. Confirm that the virtual environment is active and `PYTHONPATH` contains the repository's `src` directory.

Windows PowerShell:

```powershell
$env:PYTHONPATH = "$PWD\src"
```

macOS or Linux:

```bash
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
```

### API starts with an ephemeral JWT warning

Set a stable `MODACCT_JWT_SECRET_KEY` with at least 32 characters. The generated fallback is suitable only for temporary local demonstrations and rotates on restart.

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

Change the local port passed to Uvicorn or Streamlit. For containers, edit the host-side port mapping in `config/docker-compose.yml`.

## Scope Reminder

The default data and workflows are designed for demonstration and portfolio review. They are not production tax, treasury, bank-feed, or financial-reporting controls.
