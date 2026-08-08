from datetime import date

from apps.api.models.models import AuditLog
from apps.api.services.close_service import CloseService
from sqlmodel import select

from tests._close_helpers import close_session


def test_close_mutations_write_bounded_trusted_semantic_audit_events() -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id
        service = CloseService(session, actors.organization.id, actors.preparer.id)
        period = service.create_period("Audit period", date(2027, 7, 1), date(2027, 7, 31))
        cycle = service.create_cycle(period.id, "Audit close")
        service.start(cycle.id, cycle.version)
        entries = session.exec(
            select(AuditLog).where(AuditLog.actor_org_id == actors.organization.id).order_by(AuditLog.id)
        ).all()
        assert [entry.context["event"] for entry in entries] == [
            "period_created",
            "cycle_created",
            "cycle_started",
        ]
        assert all(entry.actor_user_id == actors.preparer.id for entry in entries)
        assert all("password" not in str(entry.after_state).lower() for entry in entries)
