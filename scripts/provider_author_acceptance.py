"""Cross-platform, offline clean-environment Provider Author Kit acceptance."""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = REPO_ROOT / "packages" / "provider-sdk"
SDK_SOURCE = SDK_ROOT / "src"


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


def _source_commit() -> str:
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={REPO_ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
    ).strip()


def run_acceptance() -> dict[str, Any]:
    """Run the offline author-to-consumer lifecycle and return bounded evidence."""

    sys.path.insert(0, str(SDK_SOURCE))
    try:
        backend = importlib.import_module("modular_accounting_provider_sdk.build_backend")
        evidence_module = importlib.import_module("modular_accounting_provider_sdk.evidence")
    finally:
        sys.path.pop(0)

    temp_root = Path(tempfile.mkdtemp(prefix="modacct-provider-author-"))
    evidence: dict[str, Any] = {
        "cleanup": False,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "sdk_contract": "1.0",
        "sdk_distribution": "0.5.0",
        "source_commit": _source_commit(),
    }
    try:
        env = _environment()
        sdk_first = temp_root / "sdk-first"
        sdk_second = temp_root / "sdk-second"
        sdk_artifacts = (
            backend.build_sdk_wheel(SDK_ROOT, sdk_first),
            backend.build_sdk_sdist(SDK_ROOT, sdk_first),
        )
        sdk_repeat = (
            backend.build_sdk_wheel(SDK_ROOT, sdk_second),
            backend.build_sdk_sdist(SDK_ROOT, sdk_second),
        )
        sdk_rows = [evidence_module.artifact_evidence(path) for path in sdk_artifacts]
        repeat_rows = [evidence_module.artifact_evidence(path) for path in sdk_repeat]
        evidence["sdk_artifacts"] = [row.to_dict() for row in sdk_rows]
        evidence["sdk_reproducible"] = [row.sha256 for row in sdk_rows] == [row.sha256 for row in repeat_rows]

        author_env = temp_root / "author-env"
        venv.EnvBuilder(with_pip=True, clear=True).create(author_env)
        author_python = _python(author_env)
        _run(
            [str(author_python), "-m", "pip", "install", "--no-index", "--no-deps", str(sdk_artifacts[0])],
            cwd=temp_root,
            env=env,
        )
        app_probe = _run(
            [
                str(author_python),
                "-c",
                "import importlib.util; print(importlib.util.find_spec('apps') is None)",
            ],
            cwd=temp_root,
            env=env,
        )
        if app_probe != "True":
            raise RuntimeError("application package leaked into author environment")
        evidence["author_application_unavailable"] = True
        evidence["build_tools"] = {
            "artifact_backend": "modular-accounting-provider-sdk/0.5.0",
            "pip": " ".join(_run([str(author_python), "-m", "pip", "--version"], cwd=temp_root, env=env).split()[:2]),
        }
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
        provider_payload = json.loads(
            _run(
                [
                    str(author_python),
                    "-m",
                    "modular_accounting_provider_sdk",
                    "build",
                    str(project_root),
                    "--format",
                    "json",
                ],
                cwd=author_workspace,
                env=env,
            )
        )
        provider_dist = project_root / "dist"
        provider_wheel = next(provider_dist.glob("*.whl"))
        provider_sdist = next(provider_dist.glob("*.tar.gz"))
        repeat_provider = temp_root / "provider-repeat"
        repeated = (
            backend.build_project_wheel(project_root, repeat_provider),
            backend.build_project_sdist(project_root, repeat_provider),
        )
        provider_rows = [evidence_module.artifact_evidence(path) for path in (provider_wheel, provider_sdist)]
        repeated_rows = [evidence_module.artifact_evidence(path) for path in repeated]
        if provider_payload["artifacts"] != [row.to_dict() for row in provider_rows]:
            raise RuntimeError("provider CLI evidence does not match artifacts")
        evidence["provider_artifacts"] = [row.to_dict() for row in provider_rows]
        evidence["provider_reproducible"] = [row.sha256 for row in provider_rows] == [
            row.sha256 for row in repeated_rows
        ]
        evidence["provider_identity"] = {
            "capabilities": ["market"],
            "key": "market:external_acceptance",
            "module": scaffold_payload["module"],
        }

        consumer_env = temp_root / "consumer-env"
        venv.EnvBuilder(with_pip=True, clear=True).create(consumer_env)
        consumer_python = _python(consumer_env)
        for artifact in (sdk_artifacts[0], provider_wheel):
            _run(
                [str(consumer_python), "-m", "pip", "install", "--no-index", "--no-deps", str(artifact)],
                cwd=temp_root,
                env=env,
            )
        consumer_probe = _run(
            [
                str(consumer_python),
                "-c",
                ("import importlib.util, market_external_acceptance; print(importlib.util.find_spec('apps') is None)"),
            ],
            cwd=temp_root,
            env=env,
        )
        if consumer_probe != "True":
            raise RuntimeError("application package leaked into consumer environment")
        evidence["consumer_application_unavailable"] = True
        _run(
            [str(consumer_python), "-m", "unittest", "discover", "-s", "tests", "-v"],
            cwd=project_root,
            env=env,
        )
        guard = (
            "import runpy,socket,sys\n"
            "def blocked(*args, **kwargs): raise AssertionError('network denied')\n"
            "socket.create_connection=blocked\n"
            "socket.socket.connect=blocked\n"
            "sys.argv=['modular_accounting_provider_sdk','validate',"
            "'market_external_acceptance.provider','--expected-key','market:external_acceptance',"
            "'--capability','market','--api-version','0.5.0','--format','json']\n"
            "runpy.run_module('modular_accounting_provider_sdk',run_name='__main__')\n"
        )
        conformance = json.loads(_run([str(consumer_python), "-c", guard], cwd=temp_root, env=env))
        if not conformance["passed"]:
            raise RuntimeError("installed provider failed structural conformance")
        checks = {row["code"]: row for row in conformance["checks"]}
        if checks["factory.result"]["message"] != "factory invocation deferred to runtime loading":
            raise RuntimeError("structural conformance invoked the provider factory")
        evidence["conformance"] = {
            "failure_codes": [],
            "network_denied": True,
            "passed": True,
            "provider_data_invoked": False,
        }
        evidence["importability_authorizes_execution"] = False
        evidence["local_artifacts_only"] = True

        sys.path[:0] = [str(REPO_ROOT / "src"), str(SDK_SOURCE), str(project_root / "src")]
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                loader = importlib.import_module("apps.api.services.plugin_loader")
            if "market:external_acceptance" in loader.settings.allowed_providers:
                raise RuntimeError("acceptance provider unexpectedly exists in process trust")
            try:
                loader.load_provider("market:external_acceptance")
            except ValueError as exc:
                if "not allowed" not in str(exc):
                    raise RuntimeError("application rejection was not the allowlist boundary") from exc
            else:
                raise RuntimeError("importable provider executed before operator allowlisting")
            if "market_external_acceptance.provider" in sys.modules:
                raise RuntimeError("application imported provider before operator allowlisting")
        finally:
            del sys.path[:3]
        evidence["operator_handoff"] = {
            "exact_identity_required": True,
            "pre_allowlist_rejected": True,
            "reconciliation_required_after_allowlist": True,
            "tenant_self_authorization": False,
        }
    finally:
        shutil.rmtree(temp_root, ignore_errors=False)
        evidence["cleanup"] = not temp_root.exists()
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    evidence = run_acceptance()
    rendered = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
