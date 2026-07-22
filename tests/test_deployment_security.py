"""Regression tests for secure local Compose deployment defaults."""

from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = REPOSITORY_ROOT / "config" / "docker-compose.yml"
CI_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"


def test_compose_publishes_services_only_on_loopback() -> None:
    compose = COMPOSE_FILE.read_text(encoding="utf-8")

    assert '"127.0.0.1:8000:8000"' in compose
    assert '"127.0.0.1:8501:8501"' in compose
    assert '\n      - "8000:8000"' not in compose
    assert '\n      - "8501:8501"' not in compose


def test_compose_requires_an_explicit_jwt_secret_without_a_fallback() -> None:
    compose = COMPOSE_FILE.read_text(encoding="utf-8")

    assert "${MODACCT_JWT_SECRET_KEY:?" in compose
    assert "${MODACCT_JWT_SECRET_KEY:-" not in compose
    assert "local-compose-demo-key" not in compose


def test_container_smoke_generates_a_test_only_secret_before_compose_validation() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    generate_step = workflow.index("Generate ephemeral Compose JWT secret")
    validate_step = workflow.index("Validate Compose configuration")

    assert generate_step < validate_step
    assert "secrets.token_urlsafe(48)" in workflow
    assert "MODACCT_JWT_SECRET_KEY=" in workflow
