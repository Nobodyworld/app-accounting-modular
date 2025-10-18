from datetime import datetime, timezone

from sqlmodel import SQLModel

from apps.api.audit import AuditActor, AuditLogger, apply_creation_metadata, get_current_actor, use_actor


class DummyRecord(SQLModel):
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by_id: int | None = None
    updated_by_id: int | None = None
    organization_id: int | None = None


def test_apply_creation_metadata_sets_timezone_aware_fields():
    actor = AuditActor(request_id="r1", user_id=42, organization_id=7, source="test", user_label="tester")
    record = DummyRecord()
    with use_actor(actor):
        apply_creation_metadata(record)

    assert record.created_at is not None and record.created_at.tzinfo is not None
    assert record.updated_at is not None and record.updated_at.tzinfo is not None
    assert record.created_by_id == 42
    assert record.updated_by_id == 42
    assert record.organization_id == 7
