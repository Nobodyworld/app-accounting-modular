COMPOSE_FILE = "config/docker-compose.yml"
ENV_EXAMPLE = "config/.env.example"
CI_WORKFLOW = ".github/workflows/ci.yml"
API_DOCKERFILE = "config/Dockerfile.api"
WEB_DOCKERFILE = "config/Dockerfile.web"


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


def test_final_images_declare_a_non_root_runtime_user() -> None:
    for path in (API_DOCKERFILE, WEB_DOCKERFILE):
        dockerfile = _read_repository_file(path)

        assert "ARG APP_UID=10001" in dockerfile
        assert "ARG APP_GID=10001" in dockerfile
        assert "USER ${APP_UID}:${APP_GID}" in dockerfile
        assert "COPY --chown=${APP_UID}:${APP_GID}" in dockerfile


def test_compose_applies_least_privilege_controls_to_both_services() -> None:
    compose = _read_repository_file(COMPOSE_FILE)
    tmpfs_mount = "/tmp:rw,noexec,nosuid,size=64m,uid=10001,gid=10001"

    assert compose.count('user: "10001:10001"') == 2
    assert compose.count("read_only: true") == 2
    assert compose.count("cap_drop:") == 2
    assert compose.count("- ALL") == 2
    assert compose.count("- no-new-privileges:true") == 2
    assert compose.count(tmpfs_mount) == 2


def test_container_smoke_inspects_built_image_and_live_runtime_identity() -> None:
    workflow = _read_repository_file(CI_WORKFLOW)
    expected_snippets = (
        "Verify least-privilege runtime",
        "docker inspect \"$container_id\" --format '{{.Image}}'",
        'docker image inspect "$image_id"',
        'exec -T "$service" id -u',
        'exec -T "$service" id -g',
        "ReadonlyRootfs",
        "no-new-privileges:true",
        "touch /data/write-ok",
        "touch /app/write-should-fail",
    )

    for snippet in expected_snippets:
        assert snippet in workflow
