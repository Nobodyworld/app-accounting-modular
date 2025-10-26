"""CLI scaffolding command tests."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from cli.macli import cli


def test_scaffold_extension_generates_files(monkeypatch) -> None:
    """The scaffold command should create a package skeleton."""

    monkeypatch.setenv("MODACCT_JWT_SECRET_KEY", "static-secret-for-tests")
    runner = CliRunner()

    with runner.isolated_filesystem():
        target_dir = Path("custom_plugins")
        result = runner.invoke(
            cli,
            [
                "scaffold-extension",
                "reporting:example",
                "--directory",
                str(target_dir),
                "--capability",
                "reporting",
                "--capability",
                "automation",
            ],
        )

        assert result.exit_code == 0, result.output
        package_root = target_dir / "reporting_example"
        assert (package_root / "__init__.py").exists()
        assert (package_root / "extension.py").exists()
        assert (package_root / "README.md").exists()
