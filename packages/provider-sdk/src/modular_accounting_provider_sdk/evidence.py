"""Bounded, deterministic, path-free artifact evidence helpers."""

from __future__ import annotations

import hashlib
import tarfile
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

_MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
_MAX_MEMBERS = 4096


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

    size = path.stat().st_size
    if size > _MAX_ARTIFACT_BYTES:
        raise ValueError("artifact exceeds evidence size limit")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_members(names: Iterable[str]) -> tuple[str, ...]:
    names = list(names)
    if len(names) > _MAX_MEMBERS:
        raise ValueError("artifact inventory exceeds member limit")
    cleaned: list[str] = []
    for name in names:
        normalized = name.replace("\\", "/").strip("/")
        if not normalized or normalized.startswith("../") or "/../" in normalized:
            raise ValueError("artifact inventory contains an unsafe member")
        if len(normalized) > 256:
            raise ValueError("artifact member name exceeds limit")
        cleaned.append(normalized)
    return tuple(sorted(cleaned))


def artifact_evidence(path: Path) -> ArtifactEvidence:
    """Return deterministic wheel or sdist evidence without filesystem paths."""

    suffixes = path.suffixes
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            inventory = _safe_members(archive.namelist())
    elif suffixes[-2:] == [".tar", ".gz"]:
        with tarfile.open(path, "r:gz") as archive:
            inventory = _safe_members(member.name for member in archive.getmembers() if member.isfile())
    else:
        raise ValueError("unsupported artifact type")
    return ArtifactEvidence(path.name, path.stat().st_size, sha256_file(path), inventory)
