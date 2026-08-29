"""Fail-closed filesystem and package-name boundaries for author artifacts."""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path

MAX_MODULE_NAME = 256

_MODULE_SEGMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class AuthorKitBoundaryError(ValueError):
    """A stable, path-free author-kit boundary failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def validate_provider_module(value: str) -> str:
    """Return a bounded dotted provider module or reject path-like input."""

    if not isinstance(value, str):
        raise AuthorKitBoundaryError("project.metadata_invalid", "provider module metadata is invalid")
    module = value.strip()
    if (
        not module
        or len(module) > MAX_MODULE_NAME
        or _CONTROL.search(module)
        or "/" in module
        or "\\" in module
        or ":" in module
    ):
        raise AuthorKitBoundaryError("project.metadata_invalid", "provider module metadata is invalid")
    segments = module.split(".")
    if (
        len(segments) < 2
        or segments[-1] != "provider"
        or any(not segment or _MODULE_SEGMENT.fullmatch(segment) is None for segment in segments)
    ):
        raise AuthorKitBoundaryError("project.metadata_invalid", "provider module metadata is invalid")
    return module


def _is_link_or_reparse(path: Path) -> bool:
    try:
        details = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        return False
    if path.is_symlink():
        return True
    attributes = getattr(details, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _require_contained(candidate: Path, root: Path) -> None:
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise AuthorKitBoundaryError("project.path_unsafe", "project path is unsafe") from exc


def resolved_directory(path: Path, *, create: bool = False) -> Path:
    """Resolve an ordinary directory without following a link at its boundary."""

    if create and not path.exists():
        path.mkdir(parents=True, exist_ok=True)
    if not path.exists() or not path.is_dir():
        raise AuthorKitBoundaryError("project.not_found", "project directory was not found")
    if _is_link_or_reparse(path):
        raise AuthorKitBoundaryError("project.path_unsafe", "project path is unsafe")
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        raise AuthorKitBoundaryError("project.path_unsafe", "project path is unsafe") from exc


def ordinary_file(root: Path, path: Path) -> Path:
    """Resolve one ordinary file contained beneath ``root`` without link traversal."""

    resolved_root = resolved_directory(root)
    lexical = path.absolute()
    try:
        relative = lexical.relative_to(root.absolute())
    except ValueError as exc:
        raise AuthorKitBoundaryError("project.path_unsafe", "project path is unsafe") from exc
    current = root.absolute()
    for part in relative.parts:
        current = current / part
        if _is_link_or_reparse(current):
            raise AuthorKitBoundaryError("project.path_unsafe", "project path is unsafe")
    try:
        resolved = path.resolve(strict=True)
        details = path.stat(follow_symlinks=False)
    except (FileNotFoundError, OSError) as exc:
        raise AuthorKitBoundaryError("project.not_found", "project file was not found") from exc
    _require_contained(resolved, resolved_root)
    if not stat.S_ISREG(details.st_mode):
        raise AuthorKitBoundaryError("project.path_unsafe", "project path is unsafe")
    return resolved


def safe_source_files(root: Path, source_root: Path) -> tuple[Path, ...]:
    """Collect ordinary source files below an expected, link-free source root."""

    resolved_root = resolved_directory(root)
    resolved_source = resolved_directory(source_root)
    _require_contained(resolved_source, resolved_root)
    rows: list[Path] = []
    for directory, names, filenames in os.walk(source_root, followlinks=False):
        directory_path = Path(directory)
        if _is_link_or_reparse(directory_path):
            raise AuthorKitBoundaryError("project.path_unsafe", "project source contains an unsafe link")
        for name in names:
            if _is_link_or_reparse(directory_path / name):
                raise AuthorKitBoundaryError("project.path_unsafe", "project source contains an unsafe link")
        for name in filenames:
            rows.append(ordinary_file(root, directory_path / name))
    return tuple(sorted(rows, key=lambda item: item.relative_to(resolved_root).as_posix()))


def validate_generated_targets(project_root: Path, targets: tuple[Path, ...]) -> None:
    """Require known scaffold targets and existing parents to remain in the project root."""

    base = project_root.parent
    resolved_base = resolved_directory(base, create=True)
    if project_root.exists() and _is_link_or_reparse(project_root):
        raise AuthorKitBoundaryError("project.path_unsafe", "generated project path is unsafe")
    if not project_root.exists():
        project_root.mkdir()
    resolved_project = resolved_directory(project_root)
    _require_contained(resolved_project, resolved_base)
    for target in targets:
        try:
            relative = target.absolute().relative_to(project_root.absolute())
        except ValueError as exc:
            raise AuthorKitBoundaryError("project.path_unsafe", "generated target is unsafe") from exc
        current = project_root
        for part in relative.parts:
            current = current / part
            if current.exists() and _is_link_or_reparse(current):
                raise AuthorKitBoundaryError("project.path_unsafe", "generated target is unsafe")
        if target.exists():
            details = target.stat(follow_symlinks=False)
            if not stat.S_ISREG(details.st_mode):
                raise AuthorKitBoundaryError("project.path_unsafe", "generated target is unsafe")
