"""Cross-platform, offline Provider Author Kit packaging and governance acceptance."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = REPO_ROOT / "packages" / "provider-sdk"
SDK_SOURCE = SDK_ROOT / "src"
SDK_DISTRIBUTION = "modular-accounting-provider-sdk"
SDK_VERSION = "0.5.0"
SDK_REQUIREMENT = f"{SDK_DISTRIBUTION}=={SDK_VERSION}"


def _python(venv_root: Path) -> Path:
    return venv_root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _environment() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PIP_NO_INDEX"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _run(command: list[str], *, cwd: Path, env: dict[str, str]) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if completed.returncode:
        raise RuntimeError(f"acceptance command failed ({completed.returncode}): {Path(command[0]).name}")
    return completed.stdout.strip()


def _git(*arguments: str) -> str:
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={REPO_ROOT.as_posix()}", *arguments],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
    ).strip()


def _commit_identity(source_head: str | None, tested_commit: str | None, expect_exact: bool) -> dict[str, object]:
    checkout_commit = _git("rev-parse", "HEAD")
    working_tree_clean = not _git("status", "--porcelain=v1", "--untracked-files=all")
    source = source_head or checkout_commit
    tested = tested_commit or checkout_commit
    for revision in (source, tested):
        _git("rev-parse", "--verify", f"{revision}^{{commit}}")
    if tested != checkout_commit:
        raise RuntimeError("tested commit identity does not match the checkout")
    source_tree = _git("rev-parse", f"{source}^{{tree}}")
    tested_tree = _git("rev-parse", f"{tested}^{{tree}}")
    trees_match = source_tree == tested_tree
    exact_head_equivalent = (source == tested or trees_match) and working_tree_clean
    if expect_exact and not exact_head_equivalent:
        raise RuntimeError("tested checkout is not exact-head equivalent")
    return {
        "exact_head_equivalent": exact_head_equivalent,
        "source_head_commit": source,
        "source_head_tree": source_tree,
        "tested_checkout_commit": tested,
        "tested_checkout_tree": tested_tree,
        "trees_match": trees_match,
        "working_tree_clean": working_tree_clean,
    }


def _pep517_wheel(
    python: Path,
    source: Path,
    output: Path,
    *,
    env: dict[str, str],
    find_links: Path | None = None,
) -> Path:
    command = [
        str(python),
        "-m",
        "pip",
        "wheel",
        "--use-pep517",
        "--no-index",
        "--no-deps",
        "--wheel-dir",
        str(output),
    ]
    if find_links is not None:
        command.extend(("--find-links", str(find_links)))
    command.append(str(source))
    _run(command, cwd=source, env=env)
    wheels = tuple(output.glob("*.whl"))
    if len(wheels) != 1:
        raise RuntimeError("PEP 517 wheel build did not produce exactly one artifact")
    return wheels[0]


def _standard_build(
    python: Path,
    source: Path,
    output: Path,
    *,
    env: dict[str, str],
    no_isolation: bool,
    find_links: Path | None = None,
) -> tuple[Path, Path]:
    build_env = env.copy()
    if find_links is not None:
        build_env["PIP_FIND_LINKS"] = str(find_links)
    command = [str(python), "-m", "build"]
    if no_isolation:
        command.append("--no-isolation")
    command.extend(("--outdir", str(output), str(source)))
    _run(command, cwd=source, env=build_env)
    wheels = tuple(output.glob("*.whl"))
    sdists = tuple(output.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise RuntimeError("standard PEP 517 build did not produce one wheel and one sdist")
    return wheels[0], sdists[0]


def _message(content: bytes) -> Any:
    return BytesParser(policy=default).parsebytes(content)


def _wheel_metadata(
    path: Path,
    *,
    expected_name: str,
    expected_version: str,
    expected_dependencies: tuple[str, ...],
    sdk: bool,
) -> dict[str, object]:
    from modular_accounting_provider_sdk import validate_wheel_record

    if not validate_wheel_record(path):
        raise RuntimeError("wheel RECORD validation failed")
    with zipfile.ZipFile(path) as archive:
        names = tuple(sorted(archive.namelist()))
        metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
        wheel_names = [name for name in names if name.endswith(".dist-info/WHEEL")]
        if len(metadata_names) != 1 or len(wheel_names) != 1:
            raise RuntimeError("wheel core metadata is incomplete")
        metadata = _message(archive.read(metadata_names[0]))
        wheel = _message(archive.read(wheel_names[0]))
        dependencies = tuple(metadata.get_all("Requires-Dist", []))
        if (
            metadata["Name"] != expected_name
            or metadata["Version"] != expected_version
            or metadata["Requires-Python"] != ">=3.12"
            or dependencies != expected_dependencies
            or wheel["Tag"] != "py3-none-any"
        ):
            raise RuntimeError("wheel metadata does not match declared project metadata")
        forbidden = ("apps/", "__pycache__", ".pyc", "tests/")
        if any(any(item in name for item in forbidden) for name in names):
            raise RuntimeError("wheel contains application, cache, or test files")
        if sdk:
            if metadata["License-Expression"] != "Apache-2.0":
                raise RuntimeError("SDK license expression is missing")
            if metadata.get_all("License-File", []) != ["LICENSE"]:
                raise RuntimeError("SDK license file metadata is missing")
            required_suffixes = (
                "modular_accounting_provider_sdk/py.typed",
                ".dist-info/entry_points.txt",
                ".dist-info/licenses/LICENSE",
            )
            if any(not any(name.endswith(suffix) for name in names) for suffix in required_suffixes):
                raise RuntimeError("SDK wheel package data is incomplete")
        return {
            "dependencies": list(dependencies),
            "name": metadata["Name"],
            "record_valid": True,
            "requires_python": metadata["Requires-Python"],
            "version": metadata["Version"],
        }


def _sdist_metadata(
    path: Path,
    *,
    expected_name: str,
    expected_version: str,
    expected_dependencies: tuple[str, ...],
    source_package: str,
    sdk: bool,
) -> dict[str, object]:
    from modular_accounting_provider_sdk import artifact_evidence

    artifact_evidence(path)
    with tarfile.open(path, "r:gz") as archive:
        members = {member.name: member for member in archive.getmembers() if member.isfile()}
        prefix = f"{expected_name}-{expected_version}"
        required = {
            f"{prefix}/pyproject.toml",
            f"{prefix}/README.md",
            f"{prefix}/PKG-INFO",
            f"{prefix}/src/{source_package}/__init__.py",
            f"{prefix}/src/{source_package}/py.typed",
        }
        if sdk:
            required.update(
                {
                    f"{prefix}/LICENSE",
                    f"{prefix}/SECURITY.md",
                    f"{prefix}/src/{source_package}/build_backend.py",
                }
            )
        if not required.issubset(members):
            raise RuntimeError("sdist source layout or rebuild material is incomplete")
        pkg_info_file = archive.extractfile(members[f"{prefix}/PKG-INFO"])
        if pkg_info_file is None:
            raise RuntimeError("sdist package metadata is unreadable")
        metadata = _message(pkg_info_file.read())
        dependencies = tuple(metadata.get_all("Requires-Dist", []))
        if (
            metadata["Name"] != expected_name
            or metadata["Version"] != expected_version
            or metadata["Requires-Python"] != ">=3.12"
            or dependencies != expected_dependencies
        ):
            raise RuntimeError("sdist metadata does not match declared project metadata")
        return {
            "dependencies": list(dependencies),
            "name": metadata["Name"],
            "requires_python": metadata["Requires-Python"],
            "src_layout": True,
            "version": metadata["Version"],
        }


def _provider_identity_metadata(wheel: Path, sdist: Path) -> dict[str, object]:
    with zipfile.ZipFile(wheel) as archive:
        names = [name for name in archive.namelist() if name.endswith(".dist-info/provider.json")]
        if len(names) != 1:
            raise RuntimeError("provider wheel identity metadata is missing or ambiguous")
        wheel_identity = json.loads(archive.read(names[0]))
    with tarfile.open(sdist, "r:gz") as archive:
        members = [member for member in archive.getmembers() if member.name.endswith("/provider-metadata.json")]
        if len(members) != 1:
            raise RuntimeError("provider sdist identity metadata is missing or ambiguous")
        source = archive.extractfile(members[0])
        if source is None:
            raise RuntimeError("provider sdist identity metadata is unreadable")
        sdist_identity = json.loads(source.read())
    expected = {
        "capabilities": ["market"],
        "distribution": "market-external-acceptance",
        "module": "market_external_acceptance.provider",
        "provider_key": "market:external_acceptance",
        "requires_python": ">=3.12",
        "sdk_dependency": SDK_REQUIREMENT,
        "version": "0.1.0",
    }
    if wheel_identity != expected or sdist_identity != expected:
        raise RuntimeError("provider wheel and sdist identity metadata do not agree")
    return expected


def _sdk_probe(python: Path, *, cwd: Path, env: dict[str, str]) -> dict[str, object]:
    probe = (
        "import importlib.metadata as m,importlib.resources as r,importlib.util,json;"
        "import modular_accounting_provider_sdk as sdk;"
        "print(json.dumps({'apps_absent':importlib.util.find_spec('apps') is None,"
        "'contract':sdk.PROVIDER_SDK_VERSION,'distribution':sdk.SDK_DISTRIBUTION_VERSION,"
        "'py_typed':r.files('modular_accounting_provider_sdk').joinpath('py.typed').is_file(),"
        "'requires':m.requires('modular-accounting-provider-sdk') or []},sort_keys=True))"
    )
    payload = json.loads(_run([str(python), "-c", probe], cwd=cwd, env=env))
    if payload != {
        "apps_absent": True,
        "contract": "1.0",
        "distribution": SDK_VERSION,
        "py_typed": True,
        "requires": [],
    }:
        raise RuntimeError("installed SDK public metadata probe failed")
    cli = _run([str(python), "-m", "modular_accounting_provider_sdk", "--version"], cwd=cwd, env=env)
    if not cli.endswith(SDK_VERSION):
        raise RuntimeError("installed SDK CLI version probe failed")
    _run([str(python), "-m", "pip", "check"], cwd=cwd, env=env)
    payload["cli"] = True
    payload["pip_check"] = True
    return payload


def _install_provider_and_validate(
    python: Path,
    artifact: Path,
    sdk_artifacts: Path,
    project_root: Path,
    *,
    env: dict[str, str],
) -> dict[str, object]:
    _run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--find-links",
            str(sdk_artifacts),
            str(artifact),
        ],
        cwd=project_root,
        env=env,
    )
    _run([str(python), "-m", "pip", "check"], cwd=project_root, env=env)
    _run([str(python), "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=project_root, env=env)
    guard = (
        "import json,runpy,socket,sys\n"
        "def blocked(*args,**kwargs): raise AssertionError('network denied')\n"
        "socket.create_connection=blocked\n"
        "socket.socket.connect=blocked\n"
        "sys.argv=['modular_accounting_provider_sdk','validate','market_external_acceptance.provider',"
        "'--expected-key','market:external_acceptance','--capability','market',"
        "'--api-version','0.5.0','--format','json']\n"
        "runpy.run_module('modular_accounting_provider_sdk',run_name='__main__')\n"
    )
    conformance = json.loads(_run([str(python), "-c", guard], cwd=project_root, env=env))
    checks = {row["code"]: row for row in conformance["checks"]}
    if (
        not conformance["passed"]
        or checks["factory.result"]["message"] != "factory invocation deferred to runtime loading"
    ):
        raise RuntimeError("installed provider structural conformance failed")
    return {
        "conformance_passed": True,
        "generated_tests_passed": True,
        "network_denied": True,
        "pip_check": True,
        "provider_data_invoked": False,
    }


def _operator_handoff(provider_wheel: Path, temp_root: Path, env: dict[str, str]) -> dict[str, object]:
    app_site = temp_root / "application-provider-site"
    _run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            "--target",
            str(app_site),
            str(provider_wheel),
        ],
        cwd=temp_root,
        env=env,
    )
    additions = [str(REPO_ROOT / "src"), str(SDK_SOURCE), str(app_site)]
    sys.path[:0] = additions
    key = "market:external_acceptance"
    module_name = "market_external_acceptance.provider"
    original_allowed: dict[str, Any] | None = None
    engine: Any | None = None
    try:
        from apps.api.config import ProviderInfo, settings
        from apps.api.models.models import Membership, Organization, TrustedProviderRegistration, User
        from apps.api.routers.providers import PolicyMutation, _service
        from apps.api.services.plugin_loader import load_provider, refresh_provider_cache
        from apps.api.services.provider_governance_service import (
            ProviderGovernanceConflictError,
            ProviderGovernanceNotFoundError,
            reconcile_trusted_catalog,
        )
        from pydantic import ValidationError
        from sqlalchemy.pool import StaticPool
        from sqlmodel import Session, SQLModel, create_engine

        original_allowed = dict(settings.allowed_providers)
        settings.allowed_providers = {}
        refresh_provider_cache()
        pre_module_absent = module_name not in sys.modules
        try:
            load_provider(key)
        except ValueError as exc:
            pre_rejected = "not allowed" in str(exc)
        else:
            pre_rejected = False
        if not pre_rejected or module_name in sys.modules:
            raise RuntimeError("provider crossed the pre-allowlist boundary")
        pre_module_not_imported = pre_module_absent and module_name not in sys.modules

        info = ProviderInfo(
            module=module_name,
            name="External Acceptance Market",
            description="Controlled local author-kit acceptance provider",
            capabilities=("market",),
        )
        settings.allowed_providers = {key: info}
        refresh_provider_cache()
        allowlisted = load_provider(key)
        if allowlisted.metadata.key != key or allowlisted.conformance is None or not allowlisted.conformance.passed:
            raise RuntimeError("exact allowlist identity did not pass runtime conformance")

        provider_module = importlib.import_module(module_name)
        original_factory = provider_module.provider
        factory_calls = 0

        def observed_factory() -> Any:
            nonlocal factory_calls
            factory_calls += 1
            return original_factory()

        provider_module.provider = observed_factory
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(engine)
        with Session(engine, expire_on_commit=False) as session:
            organization = Organization(name="Provider Author Acceptance")
            administrator = User(email="provider-author-acceptance@example.test", password_hash="not-used")
            session.add_all((organization, administrator))
            session.commit()
            session.refresh(organization)
            session.refresh(administrator)
            assert organization.id is not None and administrator.id is not None
            session.add(Membership(organization_id=organization.id, user_id=administrator.id, is_admin=True))
            session.commit()

            reconciliation = reconcile_trusted_catalog(session)
            registration = session.get(TrustedProviderRegistration, key)
            if registration is None or key not in reconciliation.changed:
                raise RuntimeError("trusted registration was not reconciled")
            persisted = registration.model_dump(mode="json")
            registration_safe = "module" not in persisted and module_name not in json.dumps(persisted, sort_keys=True)
            if not registration_safe:
                raise RuntimeError("registration persisted executable module identity")

            service, context = _service(organization.id, session, administrator)
            if not context.membership.is_admin:
                raise RuntimeError("administrator authorization was not observed")
            policy = service.update_policy(key, enabled=True, note="Controlled acceptance", expected_revision=0)
            selected_default = service.set_default("market", key, expected_revision=0)
            calls_before_resolution = factory_calls
            resolved = service.resolve_provider("market")
            if calls_before_resolution != 0 or factory_calls != 1 or resolved.metadata.key != key:
                raise RuntimeError("provider construction did not follow governance resolution")

            rejected_fields: list[str] = []
            for field in ("package", "wheel", "url", "module", "factory", "entry_point", "manifest"):
                try:
                    PolicyMutation.model_validate({"enabled": True, "revision": policy["revision"], field: "sentinel"})
                except ValidationError:
                    rejected_fields.append(field)
            if len(rejected_fields) != 7:
                raise RuntimeError("tenant policy input accepted executable identity metadata")

            settings.allowed_providers = {}
            refresh_provider_cache()
            removal = reconcile_trusted_catalog(session)
            session.refresh(registration)
            historical = service.detail(key)
            explicit_rejected = False
            default_rejected = False
            try:
                service.resolve_provider("market", key)
            except ProviderGovernanceNotFoundError:
                explicit_rejected = True
            try:
                service.resolve_provider("market")
            except ProviderGovernanceConflictError:
                default_rejected = True
            if (
                key not in removal.removed
                or registration.lifecycle_status != "REMOVED"
                or historical["process_trusted"] is not False
                or historical["effective"] is not False
                or not explicit_rejected
                or not default_rejected
                or factory_calls != 1
            ):
                raise RuntimeError("historical registration remained executable after trust removal")

        return {
            "allowlist_identity_accepted": True,
            "authorized_resolution_passed": True,
            "construction_after_authorization_and_governance": True,
            "historical_registration_non_executable": True,
            "organization_default_selected": selected_default["provider_key"] == key,
            "organization_enabled": policy["enabled"] is True,
            "pre_allowlist_module_not_imported": pre_module_not_imported,
            "pre_allowlist_rejected": pre_rejected,
            "process_trust_removed": True,
            "registration_contains_module_path": not registration_safe,
            "registration_reconciled": True,
            "runtime_conformance_passed": True,
            "tenant_self_authorization_rejected": True,
            "tenant_rejected_fields": rejected_fields,
        }
    finally:
        if original_allowed is not None:
            from apps.api.config import settings
            from apps.api.services.plugin_loader import refresh_provider_cache

            settings.allowed_providers = original_allowed
            refresh_provider_cache()
        if engine is not None:
            engine.dispose()
        for name in tuple(sys.modules):
            if name == "market_external_acceptance" or name.startswith("market_external_acceptance."):
                sys.modules.pop(name, None)
        del sys.path[: len(additions)]


def _clean_start_proof(temp_root: Path) -> dict[str, object]:
    env = _environment()
    env["MODACCT_DATABASE_URL"] = "sqlite://"
    env["PYTHONPATH"] = os.pathsep.join((str(REPO_ROOT / "src"), str(SDK_SOURCE)))
    probes = {
        "application_api": "import apps.api.main",
        "provider_facade": "import apps.provider_sdk",
    }
    for statement in probes.values():
        _run([sys.executable, "-c", statement], cwd=REPO_ROOT, env=env)
    _run([sys.executable, "-m", "cli.macli", "--help"], cwd=REPO_ROOT, env=env)
    _run([sys.executable, "-m", "modular_accounting_provider_sdk", "--version"], cwd=REPO_ROOT, env=env)
    clean_env = _environment()
    _run([sys.executable, str(REPO_ROOT / "apps" / "web" / "app.py")], cwd=temp_root, env=clean_env)
    return {
        "application_api_imported": True,
        "application_cli_help": True,
        "documented_pythonpath_used": True,
        "prior_pythonpath_removed": True,
        "provider_facade_imported": True,
        "sdk_cli_invoked": True,
        "streamlit_compatibility_launcher_imported": True,
    }


def run_acceptance(
    *,
    source_head: str | None = None,
    tested_commit: str | None = None,
    expect_exact: bool = False,
) -> dict[str, Any]:
    """Run offline builds, clean installs, governed handoff, and bounded evidence."""

    sys.path.insert(0, str(SDK_SOURCE))
    try:
        evidence_module = importlib.import_module("modular_accounting_provider_sdk.evidence")
    finally:
        sys.path.pop(0)

    temp_root = Path(tempfile.mkdtemp(prefix="modacct-provider-author-"))
    evidence: dict[str, Any] = {
        "cleanup": False,
        "identity": _commit_identity(source_head, tested_commit, expect_exact),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "sdk_contract": "1.0",
        "sdk_distribution": SDK_VERSION,
    }
    try:
        env = _environment()
        sdk_first = temp_root / "sdk-first"
        sdk_second = temp_root / "sdk-second"
        sdk_first.mkdir()
        sdk_second.mkdir()
        sdk_artifacts = _standard_build(
            Path(sys.executable),
            SDK_ROOT,
            sdk_first,
            env=env,
            no_isolation=True,
        )
        sdk_repeat = _standard_build(
            Path(sys.executable),
            SDK_ROOT,
            sdk_second,
            env=env,
            no_isolation=True,
        )
        sdk_rows = [evidence_module.artifact_evidence(path) for path in sdk_artifacts]
        repeat_rows = [evidence_module.artifact_evidence(path) for path in sdk_repeat]
        evidence["sdk_artifacts"] = [row.to_dict() for row in sdk_rows]
        evidence["sdk_reproducible"] = [row.sha256 for row in sdk_rows] == [row.sha256 for row in repeat_rows]
        evidence["sdk_metadata"] = {
            "wheel": _wheel_metadata(
                sdk_artifacts[0],
                expected_name=SDK_DISTRIBUTION,
                expected_version=SDK_VERSION,
                expected_dependencies=(),
                sdk=True,
            ),
            "sdist": _sdist_metadata(
                sdk_artifacts[1],
                expected_name=SDK_DISTRIBUTION,
                expected_version=SDK_VERSION,
                expected_dependencies=(),
                source_package="modular_accounting_provider_sdk",
                sdk=True,
            ),
        }

        extracted_sdk = evidence_module.extract_sdist_safely(sdk_artifacts[1], temp_root / "sdk-extracted")
        extracted_sdk_dist = temp_root / "sdk-extracted-dist"
        extracted_sdk_dist.mkdir()
        _pep517_wheel(Path(sys.executable), extracted_sdk, extracted_sdk_dist, env=env)

        sdk_installations: dict[str, object] = {}
        for kind, artifact in (("wheel", sdk_artifacts[0]), ("sdist", sdk_artifacts[1])):
            install_env = temp_root / f"sdk-{kind}-env"
            venv.EnvBuilder(with_pip=True, clear=True).create(install_env)
            install_python = _python(install_env)
            _run(
                [
                    str(install_python),
                    "-m",
                    "pip",
                    "install",
                    "--no-index",
                    "--find-links",
                    str(sdk_first),
                    str(artifact),
                ],
                cwd=temp_root,
                env=env,
            )
            sdk_installations[kind] = _sdk_probe(install_python, cwd=temp_root, env=env)
        evidence["sdk_installations"] = sdk_installations

        author_env = temp_root / "author-env"
        venv.EnvBuilder(with_pip=True, clear=True).create(author_env)
        author_python = _python(author_env)
        _run(
            [str(author_python), "-m", "pip", "install", "--no-index", "--no-deps", str(sdk_artifacts[0])],
            cwd=temp_root,
            env=env,
        )
        evidence["author_environment"] = _sdk_probe(author_python, cwd=temp_root, env=env)
        evidence["repository_pythonpath_absent"] = "PYTHONPATH" not in env

        author_workspace = temp_root / "author-workspace"
        author_workspace.mkdir()
        scaffold_payload = json.loads(
            _run(
                [
                    str(author_python),
                    "-m",
                    "modular_accounting_provider_sdk",
                    "scaffold",
                    "market:external_acceptance",
                    "--capability",
                    "market",
                    "--directory",
                    str(author_workspace),
                    "--format",
                    "json",
                ],
                cwd=author_workspace,
                env=env,
            )
        )
        project_root = author_workspace / scaffold_payload["distribution"]
        provider_first = temp_root / "provider-first"
        provider_second = temp_root / "provider-second"
        provider_first.mkdir()
        provider_second.mkdir()
        provider_artifacts = _standard_build(
            Path(sys.executable),
            project_root,
            provider_first,
            env=env,
            no_isolation=False,
            find_links=sdk_first,
        )
        provider_repeat = _standard_build(
            Path(sys.executable),
            project_root,
            provider_second,
            env=env,
            no_isolation=False,
            find_links=sdk_first,
        )
        provider_rows = [evidence_module.artifact_evidence(path) for path in provider_artifacts]
        repeated_rows = [evidence_module.artifact_evidence(path) for path in provider_repeat]
        evidence["provider_artifacts"] = [row.to_dict() for row in provider_rows]
        evidence["provider_reproducible"] = [row.sha256 for row in provider_rows] == [
            row.sha256 for row in repeated_rows
        ]
        provider_wheel_metadata = _wheel_metadata(
            provider_artifacts[0],
            expected_name="market-external-acceptance",
            expected_version="0.1.0",
            expected_dependencies=(SDK_REQUIREMENT,),
            sdk=False,
        )
        provider_sdist_metadata = _sdist_metadata(
            provider_artifacts[1],
            expected_name="market-external-acceptance",
            expected_version="0.1.0",
            expected_dependencies=(SDK_REQUIREMENT,),
            source_package="market_external_acceptance",
            sdk=False,
        )
        provider_identity = _provider_identity_metadata(provider_artifacts[0], provider_artifacts[1])
        evidence["provider_metadata"] = {
            "agree": all(
                provider_wheel_metadata[key] == provider_sdist_metadata[key]
                for key in ("name", "version", "requires_python", "dependencies")
            ),
            "identity_agree": True,
            "wheel": provider_wheel_metadata,
            "sdist": provider_sdist_metadata,
        }
        evidence["provider_identity"] = {
            "capabilities": provider_identity["capabilities"],
            "key": provider_identity["provider_key"],
            "module": provider_identity["module"],
        }

        extracted_provider = evidence_module.extract_sdist_safely(
            provider_artifacts[1], temp_root / "provider-extracted"
        )
        extracted_provider_dist = temp_root / "provider-extracted-dist"
        extracted_provider_dist.mkdir()
        _pep517_wheel(
            author_python,
            extracted_provider,
            extracted_provider_dist,
            env=env,
            find_links=sdk_first,
        )
        evidence["extracted_sdist_rebuilds"] = {"provider": True, "sdk": True}

        provider_installations: dict[str, object] = {}
        for kind, artifact in (("wheel", provider_artifacts[0]), ("sdist", provider_artifacts[1])):
            consumer_env = temp_root / f"provider-{kind}-env"
            venv.EnvBuilder(with_pip=True, clear=True).create(consumer_env)
            provider_installations[kind] = _install_provider_and_validate(
                _python(consumer_env), artifact, sdk_first, project_root, env=env
            )
        evidence["provider_installations"] = provider_installations
        evidence["local_artifacts_only"] = True
        evidence["build_frontend"] = {
            "provider": "python -m build with isolated local SDK build requirement",
            "sdk": "python -m build --no-isolation with in-tree backend",
        }
        evidence["operator_handoff"] = _operator_handoff(provider_artifacts[0], temp_root, env)
        evidence["clean_start"] = _clean_start_proof(temp_root)
    finally:
        shutil.rmtree(temp_root, ignore_errors=False)
        evidence["cleanup"] = not temp_root.exists()
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source-head", default=os.environ.get("PROVIDER_ACCEPTANCE_SOURCE_HEAD"))
    parser.add_argument("--tested-commit", default=os.environ.get("PROVIDER_ACCEPTANCE_TESTED_COMMIT"))
    parser.add_argument(
        "--expect-exact-head",
        action="store_true",
        default=os.environ.get("PROVIDER_ACCEPTANCE_EXPECT_EXACT_HEAD") == "1",
    )
    args = parser.parse_args()
    evidence = run_acceptance(
        source_head=args.source_head,
        tested_commit=args.tested_commit,
        expect_exact=args.expect_exact_head,
    )
    rendered = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
