import json
from pathlib import Path

from click.testing import CliRunner

from cli.macli import cli


def test_inspect_plan_command_outputs_summary(tmp_path: Path) -> None:
    plan_payload = {
        "metadata": {"name": "QA", "tags": ["ci"]},
        "defaults": {"base_currency": "USD"},
        "scenarios": [
            {"name": "baseline", "commodity_symbols": ["XAU"]},
            {"name": "eur_fx", "base_currency": "EUR"},
        ],
    }
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan_payload))

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["inspect-plan", "--plan", str(plan_path), "--format", "json"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    output_lines = [line for line in result.output.splitlines() if line.strip()]
    payload: dict[str, object]
    try:
        start = next(i for i, line in enumerate(output_lines) if line.strip() == "{")
    except StopIteration:
        payload = json.loads(output_lines[-1])
    else:
        json_block = "\n".join(output_lines[start:])
        payload, _ = json.JSONDecoder().raw_decode(json_block)
    assert payload["plan"]["metadata"]["name"] == "QA"
    assert payload["summary"]["scenario_count"] == 2
    assert sorted(payload["summary"]["base_currencies"]) == ["EUR", "USD"]
