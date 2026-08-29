"""Zero-dependency PEP 517 backend for the SDK and generated providers."""

from __future__ import annotations

import base64
import csv
import gzip
import hashlib
import io
import json
import re
import tarfile
import tomllib
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .path_safety import (
    AuthorKitBoundaryError,
    ordinary_file,
    resolved_directory,
    safe_source_files,
    validate_provider_module,
)

_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
_SDK_NAME = "modular-accounting-provider-sdk"
_SDK_VERSION = "0.5.0"
_SDK_REQUIREMENT = f"{_SDK_NAME}=={_SDK_VERSION}"
_PYTHON_REQUIREMENT = ">=3.12"


@dataclass(frozen=True, slots=True)
class _ProjectMetadata:
    name: str
    version: str
    requires_python: str
    dependencies: tuple[str, ...]
    module: str | None = None
    key: str | None = None
    capabilities: tuple[str, ...] = ()


def _load_pyproject(root: Path) -> dict[str, Any]:
    project_file = ordinary_file(root, root / "pyproject.toml")
    try:
        with project_file.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise AuthorKitBoundaryError("project.metadata_invalid", "project metadata is invalid") from exc
    return data


def _project_metadata(root: Path) -> _ProjectMetadata:
    data = _load_pyproject(root)
    project = data.get("project")
    if not isinstance(project, dict):
        raise AuthorKitBoundaryError("project.metadata_invalid", "project metadata is incomplete")
    name, version = project.get("name"), project.get("version")
    requires_python = project.get("requires-python")
    dependencies = project.get("dependencies")
    if not isinstance(name, str) or _NAME.fullmatch(name) is None:
        raise AuthorKitBoundaryError("project.metadata_invalid", "project distribution name is invalid")
    if not isinstance(version, str) or _VERSION.fullmatch(version) is None:
        raise AuthorKitBoundaryError("project.metadata_invalid", "project version is invalid")
    if (
        requires_python != _PYTHON_REQUIREMENT
        or not isinstance(dependencies, list)
        or not all(isinstance(item, str) for item in dependencies)
    ):
        raise AuthorKitBoundaryError("project.metadata_invalid", "project compatibility metadata is invalid")
    return _ProjectMetadata(name, version, requires_python, tuple(dependencies))


def _metadata(root: Path) -> _ProjectMetadata:
    data = _load_pyproject(root)
    project = data.get("project")
    provider = data.get("tool", {}).get("modular-accounting-provider")
    build_system = data.get("build-system")
    if not isinstance(project, dict) or not isinstance(provider, dict) or not isinstance(build_system, dict):
        raise AuthorKitBoundaryError("project.metadata_invalid", "project metadata is incomplete")
    base = _project_metadata(root)
    if base.name == _SDK_NAME:
        raise AuthorKitBoundaryError("project.metadata_invalid", "provider project metadata is incomplete")
    if base.dependencies != (_SDK_REQUIREMENT,):
        raise AuthorKitBoundaryError("project.metadata_invalid", "provider SDK dependency metadata is invalid")
    if build_system.get("build-backend") != "modular_accounting_provider_sdk.build_backend" or build_system.get(
        "requires"
    ) != [_SDK_REQUIREMENT]:
        raise AuthorKitBoundaryError("project.metadata_invalid", "provider build-system metadata is invalid")
    module_value = provider.get("module")
    if not isinstance(module_value, str):
        raise AuthorKitBoundaryError("project.metadata_invalid", "provider module metadata is invalid")
    module = validate_provider_module(module_value)
    key = provider.get("key")
    capabilities = provider.get("capabilities")
    if not isinstance(key, str) or not key or len(key) > 96:
        raise AuthorKitBoundaryError("project.metadata_invalid", "provider key metadata is invalid")
    if (
        not isinstance(capabilities, list)
        or not capabilities
        or not all(isinstance(item, str) and item for item in capabilities)
    ):
        raise AuthorKitBoundaryError("project.metadata_invalid", "provider capability metadata is invalid")
    return _ProjectMetadata(
        base.name,
        base.version,
        base.requires_python,
        base.dependencies,
        module,
        key,
        tuple(sorted(capabilities)),
    )


def _sdk_metadata(root: Path) -> _ProjectMetadata:
    data = _load_pyproject(root)
    metadata = _project_metadata(root)
    build_system = data.get("build-system")
    if (
        metadata.name != _SDK_NAME
        or metadata.version != _SDK_VERSION
        or metadata.dependencies
        or project_license(data) != "Apache-2.0"
        or not isinstance(build_system, dict)
        or build_system.get("requires") != []
        or build_system.get("build-backend") != "modular_accounting_provider_sdk.build_backend"
        or build_system.get("backend-path") != ["src"]
    ):
        raise AuthorKitBoundaryError("project.metadata_invalid", "SDK package metadata is inconsistent")
    return metadata


def project_license(data: dict[str, Any]) -> object:
    project = data.get("project")
    return project.get("license") if isinstance(project, dict) else None


def _source_files(root: Path, package: str) -> tuple[tuple[str, bytes], ...]:
    package_root = root / "src" / package
    if not package_root.exists():
        raise AuthorKitBoundaryError("project.not_found", "provider source package is missing")
    rows: list[tuple[str, bytes]] = []
    resolved_root = resolved_directory(root)
    for path in safe_source_files(root, package_root):
        if path.suffix == ".py" or path.name == "py.typed":
            relative = path.relative_to(resolved_root / "src").as_posix()
            rows.append((relative, path.read_bytes().replace(b"\r\n", b"\n")))
    if not rows:
        raise AuthorKitBoundaryError("project.metadata_invalid", "provider source package is empty")
    return tuple(rows)


def _wheel_hash(content: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=")
    return f"sha256={digest.decode('ascii')}"


def _zip_write(archive: zipfile.ZipFile, name: str, content: bytes) -> None:
    info = zipfile.ZipInfo(name, _ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    archive.writestr(info, content)


def _core_metadata(metadata: _ProjectMetadata, *, license_expression: str | None = None) -> bytes:
    dependencies = "".join(f"Requires-Dist: {value}\n" for value in metadata.dependencies)
    license_lines = f"License-Expression: {license_expression}\nLicense-File: LICENSE\n" if license_expression else ""
    return (
        "Metadata-Version: 2.4\n"
        f"Name: {metadata.name}\n"
        f"Version: {metadata.version}\n"
        f"Requires-Python: {metadata.requires_python}\n"
        f"{license_lines}{dependencies}"
    ).encode()


def _provider_identity(metadata: _ProjectMetadata) -> bytes:
    return (
        json.dumps(
            {
                "capabilities": list(metadata.capabilities),
                "distribution": metadata.name,
                "module": metadata.module,
                "provider_key": metadata.key,
                "requires_python": metadata.requires_python,
                "sdk_dependency": _SDK_REQUIREMENT,
                "version": metadata.version,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()


def _write_wheel(
    output_directory: Path,
    *,
    metadata: _ProjectMetadata,
    files: list[tuple[str, bytes]],
    entry_points: bytes | None = None,
    license_content: bytes | None = None,
    provider_identity: bytes | None = None,
) -> Path:
    normalized = metadata.name.replace("-", "_")
    dist_info = f"{normalized}-{metadata.version}.dist-info"
    files.extend(
        (
            (
                f"{dist_info}/METADATA",
                _core_metadata(metadata, license_expression="Apache-2.0" if license_content else None),
            ),
            (
                f"{dist_info}/WHEEL",
                b"Wheel-Version: 1.0\nGenerator: modular-accounting-provider-sdk 0.5.0\n"
                b"Root-Is-Purelib: true\nTag: py3-none-any\n",
            ),
        )
    )
    if entry_points is not None:
        files.append((f"{dist_info}/entry_points.txt", entry_points))
    if license_content is not None:
        files.append((f"{dist_info}/licenses/LICENSE", license_content))
    if provider_identity is not None:
        files.append((f"{dist_info}/provider.json", provider_identity))
    member_names = [name for name, _ in files]
    if len(member_names) != len(set(member_names)):
        raise AuthorKitBoundaryError("artifact.member_unsafe", "artifact contains duplicate members")
    rows = [(name, _wheel_hash(content), str(len(content))) for name, content in files]
    record_name = f"{dist_info}/RECORD"
    record_buffer = io.StringIO(newline="")
    csv.writer(record_buffer, lineterminator="\n").writerows((*rows, (record_name, "", "")))
    files.append((record_name, record_buffer.getvalue().encode()))
    output = resolved_directory(output_directory, create=True)
    artifact = output / f"{normalized}-{metadata.version}-py3-none-any.whl"
    with zipfile.ZipFile(artifact, "w") as archive:
        for member, content in sorted(files):
            _zip_write(archive, member, content)
    return artifact


def build_project_wheel(root: Path, output_directory: Path) -> Path:
    """Build an installable, deterministic provider wheel."""

    metadata = _metadata(root)
    assert metadata.module is not None
    package = metadata.module.rsplit(".", 1)[0]
    return _write_wheel(
        output_directory,
        metadata=metadata,
        files=list(_source_files(root, package)),
        provider_identity=_provider_identity(metadata),
    )


def _tar_add(archive: tarfile.TarFile, name: str, content: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(content)
    info.mtime = 0
    info.mode = 0o644
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    archive.addfile(info, io.BytesIO(content))


def _write_sdist(output_directory: Path, metadata: _ProjectMetadata, members: list[tuple[str, bytes]]) -> Path:
    prefix = f"{metadata.name}-{metadata.version}"
    names = [name for name, _ in members]
    if len(names) != len(set(names)):
        raise AuthorKitBoundaryError("artifact.member_unsafe", "artifact contains duplicate members")
    output = resolved_directory(output_directory, create=True)
    artifact = output / f"{prefix}.tar.gz"
    with artifact.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for member, content in sorted(members):
                    _tar_add(archive, f"{prefix}/{member}", content)
    return artifact


def build_project_sdist(root: Path, output_directory: Path) -> Path:
    """Build a deterministic provider source distribution with its ``src`` layout."""

    metadata = _metadata(root)
    assert metadata.module is not None
    package = metadata.module.rsplit(".", 1)[0]
    members = [(f"src/{name}", content) for name, content in _source_files(root, package)]
    for filename in ("pyproject.toml", "README.md"):
        path = ordinary_file(root, root / filename)
        members.append((filename, path.read_bytes().replace(b"\r\n", b"\n")))
    members.extend(
        (
            ("PKG-INFO", _core_metadata(metadata)),
            ("provider-metadata.json", _provider_identity(metadata)),
        )
    )
    return _write_sdist(output_directory, metadata, members)


def _sdk_files(root: Path) -> tuple[tuple[str, bytes], ...]:
    source = root / "src" / "modular_accounting_provider_sdk"
    if not source.exists():
        raise AuthorKitBoundaryError("project.not_found", "SDK source package is missing")
    resolved_root = resolved_directory(root)
    rows = [
        (
            path.relative_to(resolved_root / "src").as_posix(),
            path.read_bytes().replace(b"\r\n", b"\n"),
        )
        for path in safe_source_files(root, source)
        if path.suffix == ".py" or path.name == "py.typed"
    ]
    if not rows:
        raise AuthorKitBoundaryError("project.metadata_invalid", "SDK source package is empty")
    return tuple(rows)


def build_sdk_wheel(root: Path, output_directory: Path) -> Path:
    """Build the authoritative SDK wheel used by the declared PEP 517 hook."""

    metadata = _sdk_metadata(root)
    entry_points = b"[console_scripts]\nmodular-accounting-provider-sdk = modular_accounting_provider_sdk.cli:main\n"
    license_content = ordinary_file(root, root / "LICENSE").read_bytes().replace(b"\r\n", b"\n")
    return _write_wheel(
        output_directory,
        metadata=metadata,
        files=list(_sdk_files(root)),
        entry_points=entry_points,
        license_content=license_content,
    )


def build_sdk_sdist(root: Path, output_directory: Path) -> Path:
    """Build the authoritative, rebuildable SDK source distribution."""

    metadata = _sdk_metadata(root)
    members = [(f"src/{name}", content) for name, content in _sdk_files(root)]
    for filename in ("pyproject.toml", "README.md", "LICENSE", "SECURITY.md"):
        path = ordinary_file(root, root / filename)
        members.append((filename, path.read_bytes().replace(b"\r\n", b"\n")))
    members.append(("PKG-INFO", _core_metadata(metadata, license_expression="Apache-2.0")))
    return _write_sdist(output_directory, metadata, members)


def _is_sdk_project(root: Path) -> bool:
    return _project_metadata(root).name == _SDK_NAME


def build_wheel(
    wheel_directory: str,
    config_settings: dict[str, Any] | None = None,
    metadata_directory: str | None = None,
) -> str:
    """PEP 517 wheel hook for the SDK source or a generated provider."""

    del config_settings, metadata_directory
    root = Path.cwd()
    builder = build_sdk_wheel if _is_sdk_project(root) else build_project_wheel
    return builder(root, Path(wheel_directory)).name


def build_sdist(sdist_directory: str, config_settings: dict[str, Any] | None = None) -> str:
    """PEP 517 sdist hook for the SDK source or a generated provider."""

    del config_settings
    root = Path.cwd()
    builder = build_sdk_sdist if _is_sdk_project(root) else build_project_sdist
    return builder(root, Path(sdist_directory)).name


def get_requires_for_build_wheel(config_settings: dict[str, Any] | None = None) -> list[str]:
    del config_settings
    return []


def get_requires_for_build_sdist(config_settings: dict[str, Any] | None = None) -> list[str]:
    del config_settings
    return []
