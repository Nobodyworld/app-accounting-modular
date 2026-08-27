"""Regression coverage for authorization-first provider resolution."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from apps.api.routers import market, tax
from fastapi import HTTPException


def _call_sync(route: str) -> None:
    if route == "market":
        market.sync_prices(
            organization_id=2,
            symbol="AUDIT",
            start=date(2026, 1, 1),
            end=date(2026, 1, 2),
            provider_key="not-allowed",
            session=object(),
            current_user=SimpleNamespace(id=1),
        )
        return
    tax.sync_tax(
        organization_id=2,
        provider_key="not-allowed",
        session=object(),
        current_user=SimpleNamespace(id=1),
    )


@pytest.mark.parametrize(("route", "module"), [("market", market), ("tax", tax)])
def test_provider_discovery_waits_for_tenant_membership(monkeypatch, route, module) -> None:
    events: list[str] = []

    def deny_membership(**_kwargs):
        events.append("authorize")
        raise HTTPException(status_code=403, detail="Not authorized for this organization")

    class ForbiddenGovernance:
        def __init__(self, *_args, **_kwargs):
            events.append("provider")
            raise AssertionError("provider discovery must not run before tenant authorization")

    monkeypatch.setattr(module, "get_current_organization", deny_membership)
    monkeypatch.setattr(module, "ProviderGovernanceService", ForbiddenGovernance)

    with pytest.raises(HTTPException) as exc_info:
        _call_sync(route)

    assert exc_info.value.status_code == 403
    assert events == ["authorize"]


@pytest.mark.parametrize(("route", "module"), [("market", market), ("tax", tax)])
def test_provider_discovery_waits_for_manage_permission(monkeypatch, route, module) -> None:
    events: list[str] = []
    membership = SimpleNamespace(
        is_admin=False,
        can_manage_market=False,
        can_manage_tax=False,
    )
    organization = SimpleNamespace(id=2)

    def authorize(**_kwargs):
        events.append("authorize")
        return SimpleNamespace(membership=membership, organization=organization)

    class ForbiddenGovernance:
        def __init__(self, *_args, **_kwargs):
            events.append("provider")
            raise AssertionError("provider discovery must not run before role authorization")

    monkeypatch.setattr(module, "get_current_organization", authorize)
    monkeypatch.setattr(module, "ProviderGovernanceService", ForbiddenGovernance)

    with pytest.raises(HTTPException) as exc_info:
        _call_sync(route)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Insufficient permissions"
    assert events == ["authorize"]
