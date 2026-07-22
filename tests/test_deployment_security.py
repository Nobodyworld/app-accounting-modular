COMPOSE_FILE = "config/docker-compose.yml"
ENV_EXAMPLE = "config/.env.example"
CI_WORKFLOW = ".github/workflows/ci.yml"


def _read_repository_file(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def test_compose_publishes_services_only_on_loopback() -> None:
    compose = _read_repository_file(COMPOSE_FILE)

    assert '"127.0.0.1:8000:8000"' in compose
    assert '"127.0.0.1:8501:8501"' in compose
    assert '\n      - "8000:8000"' not in compose
    assert '\n      - "8501:8501"' not in compose


def test_compose_requires_an_explicit_jwt_secret_without_a_fallback() -> None:
    compose = _read_repository_file(COMPOSE_FILE)

    assert "${MODACCT_JWT_SECRET_KEY:?" in compose
    assert "${MODACCT_JWT_SECRET_KEY:-" not in compose
    assert "local-compose-demo-key" not in compose


def test_environment_example_does_not_ship_a_repository_known_jwt_secret() -> None:
    env_lines = _read_repository_file(ENV_EXAMPLE).splitlines()
    jwt_lines = [line for line in env_lines if line.startswith("MODACCT_JWT_SECRET_KEY=")]

    assert jwt_lines == ["MODACCT_JWT_SECRET_KEY="]


def test_container_smoke_proves_fail_closed_then_generates_a_test_only_secret() -> None:
    workflow = _read_repository_file(CI_WORKFLOW)

    reject_step = workflow.index("Verify Compose rejects missing JWT secret")
    generate_step = workflow.index("Generate ephemeral Compose JWT secret")
    validate_step = workflow.index("Validate Compose configuration")

    assert reject_step < generate_step < validate_step
    assert "env -u MODACCT_JWT_SECRET_KEY" in workflow
    assert "secrets.token_urlsafe(48)" in workflow
    assert "MODACCT_JWT_SECRET_KEY=" in workflow
