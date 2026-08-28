"""Small deterministic PEP 517 backend for generated provider projects."""

from __future__ import annotations

import base64
import csv
import gzip
import hashlib
import io
import re
import tarfile
import tomllib
import zipfile
from pathlib import Path
from typing import Any

_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_VERSION = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
_SDK_NAME = "modular-accounting-provider-sdk"
_SDK_VERSION = "0.5.0"


def _metadata(root: Path) -> tuple[str, str, str, str]:
    with (root / "pyproject.toml").open("rb") as handle:
        data = tomllib.load(handle)
    project = data.get("project")
    provider = data.get("tool", {}).get("modular-accounting-provider")
    if not isinstance(project, dict) or not isinstance(provider, dict):
        raise ValueError("project metadata is incomplete")
    name, version = project.get("name"), project.get("version")
    module, key = provider.get("module"), provider.get("key")
    if not isinstance(name, str) or _NAME.fullmatch(name) is None:
        raise ValueError("project distribution name is invalid")
    if not isinstance(version, str) or _VERSION.fullmatch(version) is None:
        raise ValueError("project version is invalid")
    if not isinstance(module, str) or not module.endswith(".provider"):
        raise ValueError("provider module metadata is invalid")
    if not isinstance(key, str) or len(key) > 96:
        raise ValueError("provider key metadata is invalid")
    return name, version, module.rsplit(".", 1)[0], key


def _source_files(root: Path, package: str) -> tuple[tuple[str, bytes], ...]:
    package_root = root / "src" / package
    if not package_root.is_dir():
        raise ValueError("provider source package is missing")
    rows: list[tuple[str, bytes]] = []
    for path in sorted(package_root.rglob("*")):
        if path.is_file() and (path.suffix == ".py" or path.name == "py.typed"):
            relative = path.relative_to(root / "src").as_posix()
            rows.append((relative, path.read_bytes().replace(b"\r\n", b"\n")))
    if not rows:
        raise ValueError("provider source package is empty")
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


def _write_wheel(
    output_directory: Path,
    *,
    name: str,
    version: str,
    files: list[tuple[str, bytes]],
    requires: tuple[str, ...] = (),
    entry_points: bytes | None = None,
) -> Path:
    normalized = name.replace("-", "_")
    dist_info = f"{normalized}-{version}.dist-info"
    requires_dist = "".join(f"Requires-Dist: {value}\n" for value in requires)
    metadata = (
        f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\nRequires-Python: >=3.12\n{requires_dist}\n"
    ).encode()
    wheel = (
        b"Wheel-Version: 1.0\n"
        b"Generator: modular-accounting-provider-sdk 0.5.0\n"
        b"Root-Is-Purelib: true\n"
        b"Tag: py3-none-any\n"
    )
    files.extend(((f"{dist_info}/METADATA", metadata), (f"{dist_info}/WHEEL", wheel)))
    if entry_points is not None:
        files.append((f"{dist_info}/entry_points.txt", entry_points))
    rows = [(name_, _wheel_hash(content), str(len(content))) for name_, content in files]
    record_name = f"{dist_info}/RECORD"
    record_buffer = io.StringIO(newline="")
    csv.writer(record_buffer, lineterminator="\n").writerows((*rows, (record_name, "", "")))
    files.append((record_name, record_buffer.getvalue().encode()))
    output_directory.mkdir(parents=True, exist_ok=True)
    artifact = output_directory / f"{normalized}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(artifact, "w") as archive:
        for member, content in sorted(files):
            _zip_write(archive, member, content)
    return artifact


def build_project_wheel(root: Path, output_directory: Path) -> Path:
    """Build an installable, deterministic pure-Python wheel."""

    name, version, package, _ = _metadata(root)
    return _write_wheel(
        output_directory,
        name=name,
        version=version,
        files=list(_source_files(root, package)),
        requires=("modular-accounting-provider-sdk==0.5.0",),
    )


def _tar_add(archive: tarfile.TarFile, name: str, content: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(content)
    info.mtime = 0
    info.mode = 0o644
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    archive.addfile(info, io.BytesIO(content))


def build_project_sdist(root: Path, output_directory: Path) -> Path:
    """Build a deterministic source distribution."""

    name, version, package, _ = _metadata(root)
    prefix = f"{name}-{version}"
    members = list(_source_files(root, package))
    for filename in ("pyproject.toml", "README.md"):
        path = root / filename
        members.append((filename, path.read_bytes().replace(b"\r\n", b"\n")))
    output_directory.mkdir(parents=True, exist_ok=True)
    artifact = output_directory / f"{name}-{version}.tar.gz"
    with artifact.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for member, content in sorted(members):
                    _tar_add(archive, f"{prefix}/{member}", content)
    return artifact


def _sdk_files(root: Path) -> tuple[tuple[str, bytes], ...]:
    source = root / "src" / "modular_accounting_provider_sdk"
    rows: list[tuple[str, bytes]] = []
    for path in sorted(source.rglob("*")):
        if path.is_file() and (path.suffix == ".py" or path.name == "py.typed"):
            rows.append((path.relative_to(root / "src").as_posix(), path.read_bytes().replace(b"\r\n", b"\n")))
    if not rows:
        raise ValueError("SDK source package is empty")
    return tuple(rows)


def build_sdk_wheel(root: Path, output_directory: Path) -> Path:
    """Build the standalone SDK wheel without an external build frontend."""

    entry_points = b"[console_scripts]\nmodular-accounting-provider-sdk = modular_accounting_provider_sdk.cli:main\n"
    files = list(_sdk_files(root))
    files.append(
        (
            "modular_accounting_provider_sdk-0.5.0.dist-info/licenses/LICENSE",
            (root / "LICENSE").read_bytes().replace(b"\r\n", b"\n"),
        )
    )
    return _write_wheel(
        output_directory,
        name=_SDK_NAME,
        version=_SDK_VERSION,
        files=files,
        entry_points=entry_points,
    )


def build_sdk_sdist(root: Path, output_directory: Path) -> Path:
    """Build the standalone SDK source distribution deterministically."""

    prefix = f"{_SDK_NAME}-{_SDK_VERSION}"
    members = list(_sdk_files(root))
    for filename in ("pyproject.toml", "README.md", "LICENSE", "SECURITY.md"):
        path = root / filename
        members.append((filename, path.read_bytes().replace(b"\r\n", b"\n")))
    output_directory.mkdir(parents=True, exist_ok=True)
    artifact = output_directory / f"{prefix}.tar.gz"
    with artifact.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for member, content in sorted(members):
                    _tar_add(archive, f"{prefix}/{member}", content)
    return artifact


def build_wheel(
    wheel_directory: str,
    config_settings: dict[str, Any] | None = None,
    metadata_directory: str | None = None,
) -> str:
    """PEP 517 wheel hook."""

    del config_settings, metadata_directory
    return build_project_wheel(Path.cwd(), Path(wheel_directory)).name


def build_sdist(sdist_directory: str, config_settings: dict[str, Any] | None = None) -> str:
    """PEP 517 sdist hook."""

    del config_settings
    return build_project_sdist(Path.cwd(), Path(sdist_directory)).name


def get_requires_for_build_wheel(config_settings: dict[str, Any] | None = None) -> list[str]:
    del config_settings
    return []


def get_requires_for_build_sdist(config_settings: dict[str, Any] | None = None) -> list[str]:
    del config_settings
    return []
