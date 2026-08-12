"""Offline structural verification for container dependency lock artifacts."""

from __future__ import annotations

import argparse
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
RUNTIME_INPUT: Final = "requirements.txt"
RUNTIME_LOCK: Final = "requirements-container.lock"
TOOL_LOCK: Final = "requirements-lock-tools.lock"

BASE_IMAGE: Final = "python:3.14-slim@sha256:a7fb1e634c4a578f9e0bd6327f11a3cde11b7a9395f48e24360c0988bcc5c2bc"
GENERATOR_NAME: Final = "uv"
GENERATOR_VERSION: Final = "0.12.0"
PYTHON_POLICY: Final = "3.14"
PLATFORM_POLICY: Final = "linux/amd64 (x86_64-manylinux_2_28)"
UV_LINUX_WHEEL_SHA256: Final = "cbff74f884846d794713670faf8abe10db3bd70c43b01e63223f74eb7d958689"

REQUIRED_RUNTIME_DEPENDENCIES: Final = frozenset(
    {
        "apscheduler",
        "fastapi",
        "httpx",
        "numpy",
        "pandas",
        "passlib",
        "prometheus-client",
        "pydantic",
        "pyjwt",
        "python-dateutil",
        "python-dotenv",
        "python-multipart",
        "requests",
        "scikit-learn",
        "sqlmodel",
        "statsmodels",
        "streamlit",
        "uvicorn",
        "yfinance",
    }
)
REQUIRED_EXTRAS: Final = {
    "pyjwt": frozenset({"crypto"}),
    "uvicorn": frozenset({"standard"}),
}

_HEADER_RE = re.compile(r"^# (?P<key>[a-z][a-z0-9-]*): (?P<value>.+)$")
_HASH_RE = re.compile(r"(?:^|\s)--hash=sha256:(?P<digest>[0-9a-f]{64})(?=\s|$)")
_ANY_HASH_RE = re.compile(r"(?:^|\s)--hash=(?P<value>[^\s]+)")
_EXACT_REQUIREMENT_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)"
    r"(?P<extras>\[[A-Za-z0-9_,.-]+\])?"
    r"==(?P<version>[^\s;]+)"
    r"(?:\s*;\s*(?P<marker>.+))?$"
)
_CONCRETE_VERSION_RE = re.compile(
    r"^(?:[0-9]+!)?"
    r"[0-9]+(?:\.[0-9]+)*"
    r"(?:(?:a|b|rc)[0-9]+)?"
    r"(?:\.post[0-9]+)?"
    r"(?:\.dev[0-9]+)?"
    r"(?:\+[a-z0-9]+(?:[._-][a-z0-9]+)*)?$",
    re.IGNORECASE,
)
_FORBIDDEN_SOURCE_RE = re.compile(
    r"(^|\s)(?:-e|--editable)(?:\s|=)|(?:git|hg|svn|bzr)\+|\s@\s|https?://|file://",
    re.IGNORECASE,
)
_FORBIDDEN_OPTION_PREFIXES: Final = (
    "--extra-index-url",
    "--find-links",
    "--index-url",
    "--trusted-host",
)


class LockValidationError(ValueError):
    """Raised when a dependency lock violates the repository policy."""


@dataclass(frozen=True, slots=True)
class LockedRequirement:
    name: str
    version: str
    extras: frozenset[str]
    marker: str | None
    hashes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LockSummary:
    path: Path
    sha256: str
    requirement_count: int
    direct_requirement_count: int
    transitive_requirement_count: int
    package_versions: dict[str, str]


def canonicalize_name(name: str) -> str:
    """Return the canonical project name form used by Python packaging."""

    return re.sub(r"[-_.]+", "-", name).lower()


def canonical_text_bytes(data: bytes) -> bytes:
    """Normalize only line endings so fingerprints are stable across checkouts."""

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LockValidationError("dependency manifests must be UTF-8") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def canonical_sha256(data: bytes) -> str:
    return hashlib.sha256(canonical_text_bytes(data)).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_headers(text: str) -> tuple[dict[str, str], list[str]]:
    headers: dict[str, str] = {}
    errors: list[str] = []
    for line in text.splitlines():
        match = _HEADER_RE.fullmatch(line)
        if not match:
            continue
        key = match.group("key")
        if key in headers:
            errors.append(f"duplicate metadata field: {key}")
            continue
        headers[key] = match.group("value")
    return headers, errors


def _logical_requirement_lines(text: str) -> tuple[list[str], list[str]]:
    logical_lines: list[str] = []
    errors: list[str] = []
    current: list[str] = []

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            if current:
                errors.append(f"line {line_number}: comment or blank line interrupts a continued requirement")
                current = []
            continue

        continued = stripped.endswith("\\")
        fragment = stripped[:-1].rstrip() if continued else stripped
        current.append(fragment)
        if not continued:
            logical_lines.append(" ".join(current))
            current = []

    if current:
        errors.append("unterminated requirement continuation at end of lock")
    return logical_lines, errors


def _parse_requirements(text: str) -> tuple[list[LockedRequirement], list[str]]:
    logical_lines, errors = _logical_requirement_lines(text)
    requirements: list[LockedRequirement] = []
    seen: set[str] = set()

    for logical_line in logical_lines:
        lowered = logical_line.lower()
        if lowered.startswith(_FORBIDDEN_OPTION_PREFIXES):
            errors.append(f"mutable package-index option is forbidden: {logical_line}")
            continue
        if _FORBIDDEN_SOURCE_RE.search(logical_line):
            errors.append(f"editable, VCS, or direct URL requirement is forbidden: {logical_line}")
            continue

        all_hash_tokens = _ANY_HASH_RE.findall(logical_line)
        sha256_hashes = tuple(_HASH_RE.findall(logical_line))
        if len(all_hash_tokens) != len(sha256_hashes):
            errors.append(f"only lowercase SHA-256 hashes are allowed: {logical_line}")
        if not sha256_hashes:
            errors.append(f"requirement has no SHA-256 hash: {logical_line}")
        if len(set(sha256_hashes)) != len(sha256_hashes):
            errors.append(f"requirement contains a duplicate hash: {logical_line}")

        requirement_text = _HASH_RE.sub("", logical_line).strip()
        match = _EXACT_REQUIREMENT_RE.fullmatch(requirement_text)
        if not match:
            errors.append(f"requirement is not an exact name==version entry: {requirement_text}")
            continue

        version = match.group("version")
        if not _CONCRETE_VERSION_RE.fullmatch(version):
            errors.append(f"requirement version is not a concrete PEP 440 version: {requirement_text}")
            continue

        name = canonicalize_name(match.group("name"))
        if name in seen:
            errors.append(f"duplicate requirement entry: {name}")
            continue
        seen.add(name)

        raw_extras = match.group("extras")
        extras = frozenset(part.strip().lower() for part in raw_extras[1:-1].split(",")) if raw_extras else frozenset()
        requirements.append(
            LockedRequirement(
                name=name,
                version=version,
                extras=extras,
                marker=match.group("marker"),
                hashes=sha256_hashes,
            )
        )

    if not logical_lines:
        errors.append("lock contains no installable requirements")
    return requirements, errors


def _require_metadata(headers: dict[str, str], expected: dict[str, str]) -> list[str]:
    errors: list[str] = []
    for key, expected_value in expected.items():
        actual = headers.get(key)
        if actual is None:
            errors.append(f"missing metadata field: {key}")
        elif actual != expected_value:
            errors.append(f"metadata {key!r} is {actual!r}; expected {expected_value!r}")
    return errors


def validate_container_lock_text(lock_text: str, input_bytes: bytes) -> list[LockedRequirement]:
    """Validate runtime lock text without network access or file mutation."""

    headers, errors = _parse_headers(lock_text)
    expected_metadata = {
        "input-file": RUNTIME_INPUT,
        "input-sha256": canonical_sha256(input_bytes),
        "generator": GENERATOR_NAME,
        "generator-version": GENERATOR_VERSION,
        "python-version": PYTHON_POLICY,
        "platform": PLATFORM_POLICY,
        "base-image": BASE_IMAGE,
    }
    errors.extend(_require_metadata(headers, expected_metadata))

    requirements, requirement_errors = _parse_requirements(lock_text)
    errors.extend(requirement_errors)
    by_name = {requirement.name: requirement for requirement in requirements}

    missing = sorted(REQUIRED_RUNTIME_DEPENDENCIES - by_name.keys())
    if missing:
        errors.append(f"required top-level runtime dependencies are missing: {', '.join(missing)}")
    for name, required_extras in REQUIRED_EXTRAS.items():
        requirement = by_name.get(name)
        if requirement is not None and not required_extras.issubset(requirement.extras):
            errors.append(f"{name} must preserve extras: {', '.join(sorted(required_extras))}")

    if errors:
        raise LockValidationError("\n".join(errors))
    return requirements


def verify_container_lock(lock_path: Path, input_path: Path) -> LockSummary:
    lock_text = lock_path.read_text(encoding="utf-8")
    requirements = validate_container_lock_text(lock_text, input_path.read_bytes())
    package_versions = {requirement.name: requirement.version for requirement in requirements}
    direct_count = len(REQUIRED_RUNTIME_DEPENDENCIES)
    return LockSummary(
        path=lock_path,
        sha256=file_sha256(lock_path),
        requirement_count=len(requirements),
        direct_requirement_count=direct_count,
        transitive_requirement_count=len(requirements) - direct_count,
        package_versions=package_versions,
    )


def verify_tool_lock(lock_path: Path) -> LockSummary:
    lock_text = lock_path.read_text(encoding="utf-8")
    headers, errors = _parse_headers(lock_text)
    errors.extend(
        _require_metadata(
            headers,
            {
                "tool-package": GENERATOR_NAME,
                "tool-version": GENERATOR_VERSION,
                "python-version": PYTHON_POLICY,
                "platform": PLATFORM_POLICY,
                "base-image": BASE_IMAGE,
            },
        )
    )
    requirements, requirement_errors = _parse_requirements(lock_text)
    errors.extend(requirement_errors)
    if len(requirements) != 1:
        errors.append(f"tool lock must contain exactly one package; found {len(requirements)}")
    elif requirements[0].name != GENERATOR_NAME or requirements[0].version != GENERATOR_VERSION:
        errors.append(f"tool lock must contain only {GENERATOR_NAME}=={GENERATOR_VERSION}")
    elif requirements[0].hashes != (UV_LINUX_WHEEL_SHA256,):
        errors.append("tool lock must contain the verified uv manylinux x86_64 wheel hash")

    if errors:
        raise LockValidationError("\n".join(errors))
    return LockSummary(
        path=lock_path,
        sha256=file_sha256(lock_path),
        requirement_count=1,
        direct_requirement_count=1,
        transitive_requirement_count=0,
        package_versions={GENERATOR_NAME: GENERATOR_VERSION},
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=REPO_ROOT / RUNTIME_INPUT)
    parser.add_argument("--lock", type=Path, default=REPO_ROOT / RUNTIME_LOCK)
    parser.add_argument("--tool-lock", type=Path, default=REPO_ROOT / TOOL_LOCK)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        runtime_summary = verify_container_lock(args.lock, args.input)
        tool_summary = verify_tool_lock(args.tool_lock)
    except (LockValidationError, OSError) as exc:
        print(f"container lock verification failed:\n{exc}")
        return 1

    print(
        "container lock verified: "
        f"requirements={runtime_summary.requirement_count} "
        f"direct={runtime_summary.direct_requirement_count} "
        f"transitive={runtime_summary.transitive_requirement_count} "
        f"sha256={runtime_summary.sha256}"
    )
    print(f"lock toolchain verified: {GENERATOR_NAME}=={GENERATOR_VERSION} sha256={tool_summary.sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
