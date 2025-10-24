# Setup

Follow the steps below to install dependencies, run the demo CLI, and execute
the automated test suite.

## Prerequisites
- Python 3.11+ (tested up to 3.12; syntax remains forward-compatible with the
  planned 3.14 release)
- `pip`
- Optional: `virtualenv` or `venv`

## Installation
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## Running the Demo CLI
```bash
python -m cli.demo_cli snapshot --base USD --commodity XAU --commodity XAG --format table
```

- Use `--format json` to return the raw payload that clients receive.
- Omit `--jurisdiction` to load global tax rules, pass specific values to filter,
  or set `--jurisdiction` with an empty string to skip tax lookups entirely.

## Executing Tests & Linters
```bash
pytest
```

The snapshot service caches adapter responses by request scope, so tests focus
on validating normalisation, caching behaviour, and CLI ergonomics without
performing network calls.
