from __future__ import annotations

import pytest
from apps.api.routers import ledger
from sqlmodel import Session


class _DummyService:
    def __init__(self, session: Session, organization_id: int) -> None:
        self.session = session
        self.organization_id = organization_id


def test_service_cache_reuses_instance_per_request(monkeypatch: pytest.MonkeyPatch) -> None:
    session = Session(expire_on_commit=False)
    created: list[int] = []

    def factory(sess: Session, organization_id: int) -> _DummyService:
        created.append(organization_id)
        return _DummyService(sess, organization_id)

    monkeypatch.setattr(ledger, "LedgerService", factory)

    svc1 = ledger._service_for_org(session, 1)
    svc2 = ledger._service_for_org(session, 1)
    svc3 = ledger._service_for_org(session, 2)

    assert svc1 is svc2
    assert svc1 is not svc3
    assert created == [1, 2]
