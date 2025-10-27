from __future__ import annotations

import json
from typing import Any

from click.testing import CliRunner

from apps.observability.diagnostics import ObservabilitySnapshot
from cli.macli import cli


def test_cli_observe_json(monkeypatch) -> None:
    runner = CliRunner()

    snapshot = ObservabilitySnapshot(
        generated_at="2025-11-03T12:00:00Z",
        metrics={"lines": 3, "bytes": 42, "checks": ["database", "extensions"]},
        health={"reports": [], "by_severity": {}},
        incidents=[],
        tracing={"enabled": True, "exporter": "console", "otel_enabled": False},
        extensions=[],
    )

    async def _fake_collect(*, extension_status_provider: Any | None = None) -> ObservabilitySnapshot:
        return snapshot

    monkeypatch.setattr("cli.macli.collect_observability_snapshot", _fake_collect)
    monkeypatch.setattr("cli.macli.load_configured_extensions", lambda: [])

    result = runner.invoke(cli, ["observe", "--format", "json"])

    assert result.exit_code == 0
    parts = result.output.split("\n", 1)
    json_body = parts[1] if len(parts) == 2 else parts[0]
    payload = json.loads(json_body)
    assert payload["generated_at"] == "2025-11-03T12:00:00Z"
    assert payload["metrics"]["lines"] == 3
