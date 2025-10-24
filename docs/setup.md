# Setup

Follow the steps below to install dependencies and run the demo CLI.

## Prerequisites
- Python 3.11+
- `pip`
- Optional: `virtualenv` or `venv`

## Installation
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running the Demo CLI
```bash
python -m cli.demo_cli snapshot --base USD --commodity XAU --commodity XAG
```

The command prints a JSON payload containing FX rates, commodity quotes, and tax rules produced by the in-memory adapters.
