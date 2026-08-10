from datetime import date

import pytest
from apps.api.models.models import Organization
from apps.api.services.close_service import CloseNotFoundError, CloseService

from tests._close_helpers import close_session


def test_cycle_and_control_lookup_never_crosses_tenant_boundary() -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id
        owner = CloseService(session, actors.organization.id, actors.preparer.id)
        period = owner.create_period("Tenant period", date(2027, 6, 1), date(2027, 6, 30))
        cycle = owner.create_cycle(period.id, "Tenant close")
        other = Organization(name="Isolated tenant")
        session.add(other)
        session.commit()
        session.refresh(other)
        isolated = CloseService(session, other.id, actors.preparer.id)
        with pytest.raises(CloseNotFoundError, match="not found"):
            isolated.require_cycle(cycle.id)
