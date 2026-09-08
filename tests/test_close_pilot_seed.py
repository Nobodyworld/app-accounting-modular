"""The UI seed must not target user databases or misattribute reviewer evidence."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from apps.api.models.models import AuditLog, User
from scripts import seed_close_demo as seed
from sqlalchemy.engine import make_url
from sqlmodel import Session, SQLModel, create_engine, select


def _configured_target(monkeypatch, url):
    monkeypatch.setenv("MODACCT_DATABASE_URL", url)
    monkeypatch.setattr(seed, "engine", SimpleNamespace(url=make_url(url)))


def test_seed_requires_explicit_new_matching_database(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("MODACCT_DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="explicitly"):
        seed._require_fresh_demo_target()
    target = tmp_path / "new-demo.db"
    _configured_target(monkeypatch, f"sqlite:///{target.as_posix()}")
    assert seed._require_fresh_demo_target() == target
    assert not target.exists()
    monkeypatch.setenv("MODACCT_DATABASE_URL", "sqlite:///different.db")
    with pytest.raises(ValueError, match="Restart"):
        seed._require_fresh_demo_target()


@pytest.mark.parametrize(
    "url",
    ["sqlite://", "sqlite:///:memory:", "postgresql://localhost/pilot", "sqlite:///file:x?uri=true"],
)
def test_seed_rejects_non_file_and_uri_targets(monkeypatch, url) -> None:
    _configured_target(monkeypatch, url)
    with pytest.raises(ValueError, match="new local SQLite file"):
        seed._require_fresh_demo_target()


def test_seed_preserves_existing_database_without_initialization(monkeypatch, tmp_path, capsys) -> None:
    target = tmp_path / "private.db"
    target.write_bytes(b"existing user database sentinel")
    _configured_target(monkeypatch, f"sqlite:///{target.as_posix()}")
    calls = []
    monkeypatch.setattr(seed, "init_db", lambda: calls.append("initialized"))
    assert seed.main() == 1
    assert not calls
    assert target.read_bytes() == b"existing user database sentinel"
    assert str(tmp_path) not in capsys.readouterr().out


def test_seed_exclusive_reservation_retains_racing_target(monkeypatch, tmp_path, capsys) -> None:
    target = tmp_path / "racing.db"

    def racing_target():
        target.write_bytes(b"created by another process")
        return target

    monkeypatch.setattr(seed, "_require_fresh_demo_target", racing_target)
    calls = []
    monkeypatch.setattr(seed, "init_db", lambda: calls.append("initialized"))
    assert seed.main() == 1
    assert not calls
    assert target.read_bytes() == b"created by another process"
    assert capsys.readouterr().out.startswith("DEMO_SEED_FAILED")


def test_seed_rejects_linked_parent_without_creating_database(monkeypatch, tmp_path) -> None:
    target = tmp_path / "new.db"
    _configured_target(monkeypatch, f"sqlite:///{target.as_posix()}")
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path == tmp_path or original(path))
    with pytest.raises(ValueError, match="linked parent"):
        seed._require_fresh_demo_target()
    assert not target.exists()


def test_seed_cli_creates_fresh_database_and_refuses_repeat(monkeypatch, tmp_path, capsys) -> None:
    target = tmp_path / "owned-demo.db"
    url = f"sqlite:///{target.as_posix()}"
    engine = create_engine(url)
    monkeypatch.setenv("MODACCT_DATABASE_URL", url)
    monkeypatch.setattr(seed, "engine", engine)
    monkeypatch.setattr(seed, "init_db", lambda: SQLModel.metadata.create_all(engine))
    try:
        assert seed.main() == 0
        assert target.is_file()
        with Session(engine) as session:
            assert len(session.exec(select(User)).all()) == 3
        captured = target.read_bytes()
        assert seed.main() == 1
        assert target.read_bytes() == captured
        assert "Controlled accountant close demo created" in capsys.readouterr().out
    finally:
        engine.dispose()


def test_seed_reviewer_audit_label_matches_decision_actor() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    try:
        with Session(engine, expire_on_commit=False) as session:
            seeded = seed.seed_close_demo(session)
            reviewer = session.exec(select(User).where(User.email == seeded["users"]["reviewer"])).one()
            review_audits = session.exec(
                select(AuditLog).where(
                    AuditLog.actor_org_id == seeded["organization_id"],
                    AuditLog.actor_user_id == reviewer.id,
                )
            ).all()
            assert len(review_audits) >= 2
            assert all(item.actor_label == reviewer.email for item in review_audits)
            assert {item.entity_name for item in review_audits} >= {"AccountReconciliation", "JournalApproval"}
    finally:
        engine.dispose()
