# Modular Accounting

A modular accounting system designed for flexibility and extensibility. Built with FastAPI for the API backend, Streamlit for the web interface, and a plugin architecture for various accounting modules like forecasting, foreign exchange, ledger management, market data, and tax calculations.

## Features

- **API Backend**: RESTful API using FastAPI for core accounting operations.
- **Web Interface**: User-friendly web app built with Streamlit.
- **CLI Tools**: Command-line interface for administrative tasks.
- **Budgeting & Forecast Reports**: Organization-aware budgeting, scheduled forecast refreshes, and downloadable budget vs actual / cashflow reports.
- **Plugin System**: Extensible plugins for FX rates (ECB), market data (Yahoo Finance), and tax calculations (OECD stub).
- **Docker Support**: Easy deployment with Docker Compose.

## Quick Start

### Prerequisites

- Python 3.8+
- Docker and Docker Compose (optional, for containerized deployment)

### Installation

1. Clone the repository:

   ```bash
   git clone <repository-url>
   cd modular-accounting
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Run the application:
   - Using Docker Compose:

     ```bash
     docker-compose up
     ```

   - Or run manually:
     - API: `cd apps/api && uvicorn main:app --reload`
     - Web: `streamlit run apps/web/app.py`

## Project Structure

- `apps/api/`: FastAPI backend
- `apps/web/`: Flask web interface
- `cli/`: Command-line tools
- `plugins/`: Plugin modules for various services
- `docs/`: Documentation
- `tests/`: Unit tests

## Documentation

For detailed documentation, see the `docs/` directory:

- [Architecture](docs/ARCHITECTURE.md)
- [Forecasting](docs/FORECASTING.md)
- [Plugins](docs/PLUGINS.md)
- [Tax Model](docs/TAX_MODEL.md)

## Contributing

Contributions are welcome! Please read the contributing guidelines in the documentation.

## License

This project is licensed under the terms specified in the LICENSE file.
