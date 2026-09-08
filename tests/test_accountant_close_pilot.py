"""The exact documented close scenario must complete without relaxed policy."""

from __future__ import annotations

import hashlib
import json
import socket
import subprocess
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest
from scripts import accountant_close_pilot as pilot


def _deny(*args, **kwargs):
    raise AssertionError("The synthetic close pilot must not use network connections")


def test_seeded_close_rehearsal_completes_offline_without_policy_overrides(monkeypatch) -> None:
    monkeypatch.setattr(socket, "create_connection", _deny)
    monkeypatch.setattr(socket.socket, "connect", _deny)
    monkeypatch.setattr(socket.socket, "connect_ex", _deny)
    monkeypatch.setattr(socket, "getaddrinfo", _deny)
    report, bundle = pilot.run_rehearsal()
    assert report["status"] == "PASS"
    assert report["acceptance_layer"] == "services"
    assert report["human_pilot"] == report["browser_acceptance"] == "NOT_RUN"
    assert report["journal_approval_mode"] == "REQUESTED_ONLY"
    assert report["final_close_balances_debit_minus_credit_usd"] == {
        "1000": "355.00",
        "4000": "-500.00",
        "6000": "145.00",
    }
    assert len(report["variances"]) == 2
    assert all(row["material"] and row["disposition"] == "EXPLAINED" for row in report["variances"])
    assert [row["stage"] for row in report["trace"]] == [
        "seeded",
        "adjustment_posted",
        "controls_completed",
        "ready_for_approval",
        "closed",
        "reopened",
    ]
    assert report["trace"][0]["blocker_codes"]
    assert report["trace"][2]["blocker_codes"] == []
    assert report["trace"][-1]["evidence_freshness"] == "STALE"
    assert report["closed_evidence"]["sha256"] == hashlib.sha256(bundle).hexdigest()
    assert report["closed_evidence"]["source_status"] == "CLOSED"
    assert report["closed_evidence"]["current_after_reopen"] is False
    with ZipFile(BytesIO(bundle)) as archive:
        assert json.loads(archive.read("readiness.json"))["state"] == "CLOSED"
        combined = b"\n".join(archive.read(name) for name in archive.namelist())
    for secret in (b"close-demo-password", b"password_hash", b"access_token", b"refresh_token"):
        assert secret not in combined
        assert secret not in json.dumps(report).encode()


def test_closed_bundle_matches_fresh_session_without_regeneration(monkeypatch) -> None:
    from apps.api.models.models import CloseEvidence
    from apps.api.services.close_evidence_service import CloseEvidenceService
    from apps.api.services.close_service import CloseService
    from sqlmodel import Session, select

    original_close = CloseService.close
    captured = []

    def close_and_reload(self, cycle_id, version):
        closed = original_close(self, cycle_id, version)
        with Session(self.s.get_bind(), expire_on_commit=False) as fresh:
            records = list(fresh.exec(select(CloseEvidence).where(CloseEvidence.cycle_id == cycle_id)))
            assert records[-1].is_final is True
            service = CloseEvidenceService(fresh, self.organization_id, self.actor_user_id)
            bundle = service.require_current_recorded_bundle(cycle_id)
            assert bundle.manifest_sha256 == records[-1].manifest_sha256
            assert service.require_current_recorded_bundle(cycle_id).content == bundle.content
            assert len(fresh.exec(select(CloseEvidence).where(CloseEvidence.cycle_id == cycle_id)).all()) == len(
                records
            )
            captured.append(bundle.content)
        return closed

    monkeypatch.setattr(CloseService, "close", close_and_reload)
    _, final = pilot.run_rehearsal()
    assert captured == [final]


def test_rehearsal_rejects_incorrect_accounting_expectations(monkeypatch) -> None:
    monkeypatch.setattr(pilot, "EXPECTED_BALANCES", {"1000": "999.00", "4000": "-500.00", "6000": "145.00"})
    with pytest.raises(pilot.PilotError, match="PILOT_BALANCE_MISMATCH"):
        pilot.run_rehearsal()


def test_command_never_overwrites_existing_output_or_reports_personal_paths(tmp_path, capsys) -> None:
    existing = tmp_path / "private-existing"
    existing.mkdir()
    sentinel = existing / "keep.txt"
    sentinel.write_text("user content", encoding="utf-8")
    assert pilot.main(["--output", str(existing)]) == 1
    assert sentinel.read_text(encoding="utf-8") == "user content"
    assert capsys.readouterr().err.strip() == "PILOT_OUTPUT_EXISTS"
    assert pilot.main(["--output", str(tmp_path / "missing-parent" / "child")]) == 1
    assert capsys.readouterr().err.strip() == "PILOT_OUTPUT_PARENT_MISSING"


def test_command_rejects_dirty_source_before_creating_output(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setattr(pilot, "_git_value", lambda *args: " M tracked.py" if args[0] == "status" else "a" * 40)
    target = tmp_path / "rehearsal"
    assert pilot.main(["--output", str(target)]) == 1
    assert not target.exists()
    assert capsys.readouterr().err.strip() == "PILOT_SOURCE_NOT_CLEAN"


def test_command_isolates_settings_and_keeps_failed_task_directory(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("MODACCT_DATABASE_URL", "sqlite:///private-user.db")
    monkeypatch.setenv("MODACCT_ENV_FILE", "private-user.env")
    monkeypatch.setenv("OPENEXCHANGERATES_APP_ID", "private-key")
    monkeypatch.setattr(pilot, "_git_value", lambda *args: "" if args[0] == "status" else "a" * 40)
    observed = {}

    def fake_run(command, **kwargs):
        observed.update(kwargs)
        return subprocess.CompletedProcess(command, 1, stdout=b"private stdout", stderr=b"private stderr")

    monkeypatch.setattr(pilot.subprocess, "run", fake_run)
    target = tmp_path / "retained-failure"
    assert pilot.main(["--output", str(target)]) == 1
    assert target.is_dir()
    assert observed["cwd"] == target
    assert observed["env"]["MODACCT_DATABASE_URL"] == "sqlite://"
    assert observed["env"]["DATABASE_URL"] == "sqlite://"
    assert observed["env"]["MODACCT_ENV_FILE"] == ""
    assert "OPENEXCHANGERATES_APP_ID" not in observed["env"]
    assert observed["env"]["PYTHONNOUSERSITE"] == "1"
    assert observed["timeout"] == 180
    assert capsys.readouterr().err.strip() == "PILOT_EXECUTION_FAILED"


def test_command_worker_writes_only_fresh_summary_and_evidence(monkeypatch, tmp_path) -> None:
    # Exercise the real child, not a mocked PASS. Git identity is injected only
    # because the enclosing quality gate may have generated working-tree output.
    monkeypatch.setattr(pilot, "_git_value", lambda *args: "" if args[0] == "status" else "b" * 40)
    target = tmp_path / "completed"
    assert pilot.main(["--output", str(target)]) == 0
    assert sorted(item.name for item in target.iterdir()) == ["close-final.zip", "close-pilot.json"]
    report = json.loads((target / "close-pilot.json").read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["network_policy"] == "python_socket_connections_denied"
    assert report["source_head"] == "b" * 40
    assert report["closed_evidence"]["sha256"] == hashlib.sha256((target / "close-final.zip").read_bytes()).hexdigest()


def test_command_rejects_symlink_parent(monkeypatch, tmp_path, capsys) -> None:
    # A platform-independent path-policy probe; the Windows runtime pass also
    # checks actual paths without requiring symlink creation privileges here.
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == tmp_path or original(path))
    assert pilot.main(["--output", str(tmp_path / "child")]) == 1
    assert capsys.readouterr().err.strip() == "PILOT_OUTPUT_LINK_REJECTED"
    assert not (tmp_path / "child").exists()
