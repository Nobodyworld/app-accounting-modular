from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from apps.provider_sdk import inspect_provider_module, normalise_provider_package, scaffold_provider


def snapshot(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_normalise_provider_package_supports_current_key_vocabulary() -> None:
    assert normalise_provider_package("tax:oecd_vat") == "tax_oecd_vat"
    assert normalise_provider_package("market:sample-feed") == "market_sample_feed"
    with pytest.raises(ValueError):
        normalise_provider_package("../unsafe")


def test_scaffold_is_deterministic_path_safe_and_lf_normalized(tmp_path: Path) -> None:
    first = tmp_path / "first" / "plugins"
    second = tmp_path / "second" / "plugins"
    kwargs = {
        "key": "bank:sample_demo",
        "capabilities": ("bank", "macro"),
        "name": "Sample Provider",
        "version": "0.3.0",
        "description": "Generated sample",
        "license": "Apache-2.0",
    }

    result_one = scaffold_provider(first, **kwargs)
    result_two = scaffold_provider(second, **kwargs)

    assert result_one.module == "plugins.bank_sample_demo.provider"
    assert result_one.package == "bank_sample_demo"
    assert snapshot(first) == snapshot(second)
    for content in snapshot(first).values():
        assert "\r" not in content
        assert str(tmp_path) not in content
    test_content = (result_one.root / "tests" / "test_conformance.py").read_text(encoding="utf-8")
    assert 'MODULE = "plugins.bank_sample_demo.provider"' in test_content


def test_generated_provider_imports_and_conforms_without_calling_data_methods(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "src"
    result = scaffold_provider(
        source_root / "plugins",
        key="test:all_capabilities",
        capabilities=("bank", "fx", "macro", "market", "tax"),
        version="0.3.0",
    )
    (source_root / "plugins" / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.syspath_prepend(str(source_root))
    importlib.invalidate_caches()

    report = inspect_provider_module(
        result.module,
        expected_key="test:all_capabilities",
        expected_capabilities=("bank", "fx", "macro", "market", "tax"),
        api_version="0.0.0",
    )

    assert report.passed, report.to_json()
    sys.modules.pop(result.module, None)


def test_scaffold_refuses_known_file_overwrite_without_force(tmp_path: Path) -> None:
    directory = tmp_path / "plugins"
    result = scaffold_provider(directory, key="tax:sample_demo", capabilities=("tax",))
    marker = result.root / "README.md"
    marker.write_text("owner content", encoding="utf-8")

    with pytest.raises(FileExistsError):
        scaffold_provider(directory, key="tax:sample_demo", capabilities=("tax",))

    scaffold_provider(directory, key="tax:sample_demo", capabilities=("tax",), force=True)
    assert marker.read_text(encoding="utf-8").startswith("# Sample Demo")


def test_force_preserves_unknown_files(tmp_path: Path) -> None:
    directory = tmp_path / "plugins"
    result = scaffold_provider(directory, key="fx:sample_demo", capabilities=("fx",))
    unknown = result.root / "owner-note.txt"
    unknown.write_text("preserve", encoding="utf-8")

    scaffold_provider(directory, key="fx:sample_demo", capabilities=("fx",), force=True)

    assert unknown.read_text(encoding="utf-8") == "preserve"


def test_scaffold_rejects_invalid_manifest_and_capability(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        scaffold_provider(tmp_path, key="bad", capabilities=("fx",))
    with pytest.raises(ValueError):
        scaffold_provider(tmp_path, key="fx:bad", capabilities=("unsupported",))
