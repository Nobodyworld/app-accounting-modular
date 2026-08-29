"""Bounded, deterministic, path-free artifact evidence helpers."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import re
import stat
import tarfile
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .path_safety import AuthorKitBoundaryError

_MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
_MAX_MEMBERS = 4096
_MAX_MEMBER_NAME = 256
_MAX_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
_DRIVE = re.compile(r"^[A-Za-z]:")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True, slots=True)
class ArtifactEvidence:
    """Secret-free evidence for one local distribution artifact."""

    name: str
    size: int
    sha256: str
    inventory: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "inventory": list(self.inventory),
            "name": self.name,
            "sha256": self.sha256,
            "size": self.size,
        }


def sha256_file(path: Path) -> str:
    """Hash a bounded artifact without retaining its content."""

    try:
        size = path.stat().st_size
    except OSError as exc:
        raise AuthorKitBoundaryError("project.not_found", "artifact was not found") from exc
    if size > _MAX_ARTIFACT_BYTES:
        raise AuthorKitBoundaryError("artifact.member_unsafe", "artifact exceeds evidence size limit")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
    except OSError as exc:
        raise AuthorKitBoundaryError("artifact.member_unsafe", "artifact could not be inspected") from exc
    return digest.hexdigest()


def _normalise_member(name: str) -> str:
    if (
        not isinstance(name, str)
        or not name
        or len(name) > _MAX_MEMBER_NAME
        or _CONTROL.search(name)
        or name.startswith(("/", "\\"))
        or _DRIVE.match(name)
    ):
        raise AuthorKitBoundaryError("artifact.member_unsafe", "artifact contains an unsafe member")
    normalized = name.replace("\\", "/")
    if normalized.startswith("//") or _DRIVE.match(normalized):
        raise AuthorKitBoundaryError("artifact.member_unsafe", "artifact contains an unsafe member")
    components = normalized.split("/")
    if any(component in ("", ".", "..") for component in components):
        raise AuthorKitBoundaryError("artifact.member_unsafe", "artifact contains an unsafe member")
    return "/".join(components)


def _safe_members(names: Iterable[str]) -> tuple[str, ...]:
    raw = list(names)
    if len(raw) > _MAX_MEMBERS:
        raise AuthorKitBoundaryError("artifact.member_unsafe", "artifact inventory exceeds member limit")
    cleaned = [_normalise_member(name) for name in raw]
    normalized_keys = [name.casefold() for name in cleaned]
    if len(normalized_keys) != len(set(normalized_keys)):
        raise AuthorKitBoundaryError("artifact.member_unsafe", "artifact contains duplicate members")
    return tuple(sorted(cleaned))


def _zip_inventory(archive: zipfile.ZipFile) -> tuple[str, ...]:
    infos = archive.infolist()
    inventory = _safe_members(info.filename.rstrip("/") for info in infos)
    aggregate = 0
    for info in infos:
        aggregate += info.file_size
        mode = (info.external_attr >> 16) & 0xFFFF
        file_type = stat.S_IFMT(mode)
        if file_type == stat.S_IFLNK or (file_type and file_type not in (stat.S_IFREG, stat.S_IFDIR)):
            raise AuthorKitBoundaryError("artifact.member_unsafe", "artifact contains a non-regular member")
    if aggregate > _MAX_UNCOMPRESSED_BYTES:
        raise AuthorKitBoundaryError("artifact.member_unsafe", "artifact expanded size exceeds limit")
    return inventory


def _tar_inventory(archive: tarfile.TarFile) -> tuple[str, ...]:
    members = archive.getmembers()
    inventory = _safe_members(member.name.rstrip("/") for member in members)
    aggregate = 0
    for member in members:
        if not (member.isfile() or member.isdir()):
            raise AuthorKitBoundaryError("artifact.member_unsafe", "artifact contains a non-regular member")
        if member.isfile():
            aggregate += member.size
    if aggregate > _MAX_UNCOMPRESSED_BYTES:
        raise AuthorKitBoundaryError("artifact.member_unsafe", "artifact expanded size exceeds limit")
    return inventory


def validate_wheel_record(path: Path) -> bool:
    """Validate every wheel RECORD hash and byte count without extracting files."""

    try:
        with zipfile.ZipFile(path) as archive:
            _zip_inventory(archive)
            record_names = [name for name in archive.namelist() if name.endswith(".dist-info/RECORD")]
            if len(record_names) != 1:
                raise AuthorKitBoundaryError("artifact.member_unsafe", "wheel RECORD is missing or ambiguous")
            record_name = record_names[0]
            rows = list(csv.reader(io.StringIO(archive.read(record_name).decode("utf-8"))))
            expected = set(archive.namelist())
            if {row[0] for row in rows if len(row) == 3} != expected:
                raise AuthorKitBoundaryError("artifact.member_unsafe", "wheel RECORD inventory is inconsistent")
            for name, digest, size in rows:
                if name == record_name:
                    if digest or size:
                        raise AuthorKitBoundaryError("artifact.member_unsafe", "wheel RECORD self-entry is invalid")
                    continue
                content = archive.read(name)
                encoded = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode("ascii")
                if digest != f"sha256={encoded}" or size != str(len(content)):
                    raise AuthorKitBoundaryError("artifact.member_unsafe", "wheel RECORD hash or size is invalid")
    except (OSError, UnicodeError, zipfile.BadZipFile) as exc:
        raise AuthorKitBoundaryError("artifact.member_unsafe", "wheel metadata is invalid") from exc
    return True


def extract_sdist_safely(path: Path, destination: Path) -> Path:
    """Extract a bounded regular-file sdist and return its single project root."""

    try:
        destination.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise AuthorKitBoundaryError("project.path_unsafe", "artifact extraction target is unsafe") from exc
    destination_root = destination.resolve(strict=True)
    try:
        with tarfile.open(path, "r:gz") as archive:
            inventory = _tar_inventory(archive)
            top_levels = {name.split("/", 1)[0] for name in inventory}
            if len(top_levels) != 1:
                raise AuthorKitBoundaryError("artifact.member_unsafe", "sdist source root is malformed")
            for member in archive.getmembers():
                normalized = _normalise_member(member.name.rstrip("/"))
                target = destination_root.joinpath(*normalized.split("/"))
                try:
                    target.relative_to(destination_root)
                except ValueError as exc:
                    raise AuthorKitBoundaryError(
                        "artifact.member_unsafe", "artifact contains an unsafe member"
                    ) from exc
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise AuthorKitBoundaryError("artifact.member_unsafe", "artifact member could not be read")
                content = source.read(_MAX_UNCOMPRESSED_BYTES + 1)
                if len(content) != member.size or len(content) > _MAX_UNCOMPRESSED_BYTES:
                    raise AuthorKitBoundaryError("artifact.member_unsafe", "artifact member size is invalid")
                target.write_bytes(content)
    except (OSError, tarfile.TarError) as exc:
        raise AuthorKitBoundaryError("artifact.member_unsafe", "artifact could not be extracted") from exc
    project_root = destination_root / next(iter(top_levels))
    if not project_root.is_dir():
        raise AuthorKitBoundaryError("artifact.member_unsafe", "sdist source root is malformed")
    return project_root


def artifact_evidence(path: Path) -> ArtifactEvidence:
    """Return deterministic wheel or sdist evidence without filesystem paths."""

    suffixes = path.suffixes
    try:
        if path.suffix == ".whl":
            with zipfile.ZipFile(path) as archive:
                inventory = _zip_inventory(archive)
        elif suffixes[-2:] == [".tar", ".gz"]:
            with tarfile.open(path, "r:gz") as archive:
                inventory = _tar_inventory(archive)
        else:
            raise AuthorKitBoundaryError("artifact.member_unsafe", "unsupported artifact type")
    except (OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        raise AuthorKitBoundaryError("artifact.member_unsafe", "artifact could not be inspected") from exc
    return ArtifactEvidence(path.name, path.stat().st_size, sha256_file(path), inventory)
