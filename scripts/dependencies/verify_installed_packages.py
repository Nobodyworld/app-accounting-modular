"""Compare an image's installed Python distributions with the committed runtime lock."""

from __future__ import annotations

import importlib.metadata

from verify_container_lock import REPO_ROOT, RUNTIME_INPUT, RUNTIME_LOCK, canonicalize_name, verify_container_lock

BASE_PROVIDED_PACKAGES = frozenset({"pip", "setuptools", "wheel"})


def main() -> int:
    summary = verify_container_lock(REPO_ROOT / RUNTIME_LOCK, REPO_ROOT / RUNTIME_INPUT)
    installed = {
        canonicalize_name(distribution.metadata["Name"]): distribution.version
        for distribution in importlib.metadata.distributions()
        if distribution.metadata["Name"]
    }

    errors: list[str] = []
    for name, expected_version in summary.package_versions.items():
        actual_version = installed.get(name)
        if actual_version != expected_version:
            errors.append(f"{name}: installed={actual_version!r} locked={expected_version!r}")

    unexpected = sorted(installed.keys() - summary.package_versions.keys() - BASE_PROVIDED_PACKAGES)
    if unexpected:
        errors.append(f"unexpected installed packages: {', '.join(unexpected)}")

    if errors:
        print("installed package inventory does not match the runtime lock:")
        for error in errors:
            print(f"- {error}")
        return 1

    base_packages = sorted(installed.keys() & BASE_PROVIDED_PACKAGES)
    print(
        f"installed package inventory matches {summary.requirement_count} locked packages; "
        f"base-provided tooling={','.join(base_packages) or 'none'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
