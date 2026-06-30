# Setup

This guide covers installing Modular Accounting, setting up your development environment, and running the application.

## Prerequisites

- **Python**: 3.12 or higher
  - Minimum supported: 3.12
  - Primary development target: 3.14
  - Latest validated: 3.14
  - CI-enforced versions: 3.12, 3.13, 3.14
- **pip**: Python package installer
- **Virtual Environment**: `venv` (built-in) or `virtualenv`
- **Optional**: Docker and Docker Compose for containerized deployment

## Installation

### Local Development

1. **Clone the repository**:

   ```bash
   git clone https://github.com/Nobodyworld/app-accounting-modular.git
   cd app-accounting-modular
   ```

2. **Create a virtual environment**:

   ```bash
   python -m venv .venv
   # On Windows:
   .venv\Scripts\activate
   # On macOS/Linux:
   source .venv/bin/activate
   ```

3. **Install dependencies**:

   ```bash
   make install
   # Or manually:
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

4. **Fresh-environment validation (recommended before release)**:

   ```bash
   python -m pip check
   python -c "import apps.api.main, cli.macli, apps.modular_accounting.application; print('imports-ok')"
   ```

### Docker Setup

For containerized development:

```bash
# Build and run with Docker Compose
docker-compose up --build

# Or run individual services
docker build -f docker/Dockerfile.api -t modacct-api .
docker build -f docker/Dockerfile.web -t modacct-web .
```

## Configuration

### Environment Variables

Create a `.env` file or set environment variables:

```bash
# Database
DATABASE_URL=sqlite:///./modular_accounting.db

# API Settings
MODACCT_API_HOST=0.0.0.0
MODACCT_API_PORT=8000

# Plugin Configuration
MODACCT_ALLOWED_PROVIDERS__fx__ecb__enabled=true
MODACCT_ALLOWED_PROVIDERS__market__yfinance__enabled=true

# Extensions
MODACCT_ALLOWED_EXTENSIONS__analytics_baseline__enabled=true
```

### Settings Reference

See `apps/api/config.py` for all available configuration options.

## Running the Application

### API Server

```bash
# Development mode with auto-reload
uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000

# Production mode
uvicorn apps.api.main:app --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000` with OpenAPI docs at `http://localhost:8000/docs`.

### Web UI

```bash
streamlit run apps.web/app.py
```

The web interface will be available at `http://localhost:8501`.

### CLI Commands

```bash
# Demo CLI for testing
python -m cli.demo_cli snapshot --base USD --commodity XAU --format table

# Operational CLI
python -m cli.macli snapshot --base USD --jurisdiction US --format json

# Health checks
python -m cli.macli health
```

## Testing

### Run Tests

```bash
# All tests
make test
# Or
pytest

# With coverage
pytest --cov=src/apps --cov=src/plugins --cov=src/cli --cov-report=html
```

### Quality Checks

```bash
# Linting, type checking, and formatting
make quality

# Individual tools
make lint    # Ruff linting
make type    # MyPy type checking
make format  # Black formatting
```

### Health Checks

```bash
# Application health
make health

# Extension inspection
python -m cli.macli inspect-extensions
python -m cli.macli inspect-contracts
```

## Development Workflow

1. **Install pre-commit hooks**:

   ```bash
   pip install pre-commit
   pre-commit install
   ```

2. **Run quality checks before committing**:

   ```bash
   make quality
   ```

3. **Test your changes**:

   ```bash
   make test
   ```

## Troubleshooting

### Common Issues

#### Import Errors

**Symptoms**: `ModuleNotFoundError` or `ImportError`
**Solutions**:

- Ensure you're in the correct virtual environment: `source .venv/bin/activate`
- Install dependencies: `make install`
- Check Python version compatibility (3.12+ required, newer versions preferred)

#### Database Connection Issues

**Symptoms**: Database-related errors on startup
**Solutions**:

- Verify `DATABASE_URL` in environment variables
- Check file permissions for SQLite database
- Ensure database directory exists and is writable
- For PostgreSQL: verify connection string and credentials

#### Plugin Loading Failures

**Symptoms**: Extensions or providers not loading
**Solutions**:

- Check plugin configuration in settings
- Verify plugin directory structure (`plugins/name/provider.py`)
- Ensure plugin dependencies are installed
- Review logs for specific error messages

#### Port Conflicts

**Symptoms**: "Address already in use" errors
**Solutions**:

- Change ports in configuration: `MODACCT_API_PORT=8001`
- Kill existing processes: `lsof -ti:8000 | xargs kill`
- Use different hosts: `MODACCT_API_HOST=127.0.0.1`

#### Test Failures

**Symptoms**: Tests failing unexpectedly
**Solutions**:

- Run tests in isolation: `pytest tests/test_specific.py`
- Check for missing test dependencies
- Verify test database is clean
- Run with verbose output: `pytest -v`

#### Performance Issues

**Symptoms**: Slow responses or high memory usage
**Solutions**:

- Check cache configuration and TTL settings
- Monitor database query performance
- Review extension loading and health checks
- Enable profiling: `python -m cProfile your_script.py`

### Diagnostic Commands

```bash
# Check environment
python --version
pip list | grep modular

# Test basic functionality
python -c "import apps.modular_accounting; print('Import OK')"

# Check database
python -c "from apps.api.db import get_session; print('DB OK')"

# Test API startup
uvicorn apps.api.main:app --dry-run

# Check plugin loading
python -m cli.macli inspect-extensions
```

### Logs and Debugging

- **API Logs**: Check console output when starting with `--reload`
- **CLI Logs**: Use `--verbose` flag for detailed output
- **Health Checks**: `make health` for system diagnostics
- **Tracing**: Enable OpenTelemetry for request tracing

### Getting Help

- **Documentation**: Check [Operations & Incident Response](operations.md)
- **Issues**: Open GitHub issues with environment details
- **Logs**: Include relevant log snippets and error messages
- **Configuration**: Share your settings (redact secrets)
