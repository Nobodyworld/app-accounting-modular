"""Shared deterministic fixtures for accountant-close tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from apps.api.models.models import Membership, Organization, User
from apps.api.security import get_password_hash
from sqlmodel import Session, SQLModel, create_engine


@dataclass(slots=True)
class CloseActors:
    organization: Organization
    preparer: User
    reviewer: User
    administrator: User


@contextmanager
def close_session() -> Iterator[tuple[Session, CloseActors]]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    try:
        organization = Organization(name="Controlled Close Demo")
        users = [
            User(email="preparer@example.test", password_hash=get_password_hash("demo-password"), name="Preparer"),
            User(email="reviewer@example.test", password_hash=get_password_hash("demo-password"), name="Reviewer"),
            User(email="admin@example.test", password_hash=get_password_hash("demo-password"), name="Administrator"),
        ]
        session.add(organization)
        session.add_all(users)
        session.commit()
        session.refresh(organization)
        for user in users:
            session.refresh(user)
        assert organization.id is not None
        assert all(user.id is not None for user in users)
        session.add_all(
            [
                Membership(
                    user_id=users[0].id,
                    organization_id=organization.id,
                    can_manage_ledger=True,
                ),
                Membership(
                    user_id=users[1].id,
                    organization_id=organization.id,
                    can_manage_ledger=True,
                ),
                Membership(
                    user_id=users[2].id,
                    organization_id=organization.id,
                    can_manage_ledger=True,
                    is_admin=True,
                ),
            ]
        )
        session.commit()
        yield session, CloseActors(organization, users[0], users[1], users[2])
    finally:
        session.close()
        engine.dispose()
