"""Cross-layer regression tests for accounting transaction integrity."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from apps.api import db
from apps.api.main import create_app
from apps.api.models.models import JournalEntry, Membership, Organization, User
from apps.api.models.models import Transaction as StoredTransaction
from apps.api.security import get_current_user
from apps.api.services.ledger_service import LedgerService
from apps.modular_accounting.domain import LedgerEntry, Money, Transaction
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

pytest.importorskip("httpx")


@contextmanager
def create_ledger_client() -> Iterator[tuple[TestClient, Any, int, dict[str, int]]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db.engine = engine
    db.connect_args = {"check_same_thread": False}
    SQLModel.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as seed:
        organization = Organization(name="Ledger Integrity Org")
        user = User(email="ledger@example.com", password_hash="stub", is_active=True)
        seed.add(organization)
        seed.add(user)
        seed.commit()
        seed.refresh(organization)
        seed.refresh(user)
        assert organization.id is not None
        assert user.id is not None
        seed.add(
            Membership(
                user_id=user.id,
                organization_id=organization.id,
                is_admin=True,
                can_manage_ledger=True,
            )
        )
        seed.commit()

        ledger = LedgerService(seed, organization_id=organization.id)
        accounts = {
            "usd_cash": ledger.create_account("USD Cash", "ASSET", "1000", currency="USD").id,
            "usd_equity": ledger.create_account("USD Equity", "EQUITY", "3000", currency="USD").id,
            "eur_cash": ledger.create_account("EUR Cash", "ASSET", "1100", currency="EUR").id,
            "eur_equity": ledger.create_account("EUR Equity", "EQUITY", "3100", currency="EUR").id,
        }
        assert all(account_id is not None for account_id in accounts.values())
        typed_accounts = {name: int(account_id) for name, account_id in accounts.items()}
        user_id = user.id
        organization_id = organization.id

    app = create_app()

    def _stub_user() -> User:
        return User(
            id=user_id,
            email="ledger@example.com",
            password_hash="stub",
            is_active=True,
        )

    app.dependency_overrides[get_current_user] = _stub_user
    client = TestClient(app)
    try:
        yield client, engine, organization_id, typed_accounts
    finally:
        client.close()
        engine.dispose()


def _transaction_payload(organization_id: int, postings: list[dict[str, object]]) -> dict[str, object]:
    return {
        "date": "2026-07-12",
        "description": "Integrity regression",
        "organization_id": organization_id,
        "postings": postings,
    }


def test_empty_domain_transaction_is_not_balanced() -> None:
    transaction = Transaction(
        transaction_id="empty",
        occurred_on=date(2026, 7, 12),
        description="Empty",
    )
    assert transaction.is_balanced() is False


def test_single_domain_entry_is_not_balanced() -> None:
    transaction = Transaction(
        transaction_id="single",
        occurred_on=date(2026, 7, 12),
        description="Single",
        entries=[
            LedgerEntry(
                account_code="1000",
                amount=Money(Decimal("10.00"), "USD"),
                direction="debit",
            )
        ],
    )
    assert transaction.is_balanced() is False


def test_mixed_currency_domain_transaction_is_not_balanced() -> None:
    transaction = Transaction(
        transaction_id="mixed",
        occurred_on=date(2026, 7, 12),
        description="Mixed currencies",
        entries=[
            LedgerEntry("1000", Money(Decimal("10.00"), "USD"), "debit"),
            LedgerEntry("4000", Money(Decimal("10.00"), "EUR"), "credit"),
        ],
    )
    assert transaction.is_balanced() is False


def test_invalid_domain_direction_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported ledger entry direction"):
        LedgerEntry("1000", Money(Decimal("10.00"), "USD"), "increase")


def test_nonpositive_domain_amount_is_rejected() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        LedgerEntry("1000", Money(Decimal("0"), "USD"), "debit")


def test_api_rejects_empty_postings_and_persists_nothing() -> None:
    with create_ledger_client() as (client, engine, organization_id, _accounts):
        response = client.post("/ledger/post", json=_transaction_payload(organization_id, []))
        assert response.status_code == 422
        assert "At least two postings" in response.json()["detail"]

        with Session(engine) as session:
            assert session.exec(select(StoredTransaction)).all() == []
            assert session.exec(select(JournalEntry)).all() == []


def test_api_rejects_single_posting_and_persists_nothing() -> None:
    with create_ledger_client() as (client, engine, organization_id, accounts):
        response = client.post(
            "/ledger/post",
            json=_transaction_payload(
                organization_id,
                [{"account_id": accounts["usd_cash"], "debit": 10, "credit": 0}],
            ),
        )
        assert response.status_code == 422
        assert "At least two postings" in response.json()["detail"]

        with Session(engine) as session:
            assert session.exec(select(StoredTransaction)).all() == []
            assert session.exec(select(JournalEntry)).all() == []


def test_api_rejects_mixed_currency_transaction() -> None:
    with create_ledger_client() as (client, _engine, organization_id, accounts):
        response = client.post(
            "/ledger/post",
            json=_transaction_payload(
                organization_id,
                [
                    {"account_id": accounts["usd_cash"], "debit": 10, "credit": 0},
                    {"account_id": accounts["eur_equity"], "debit": 0, "credit": 10},
                ],
            ),
        )
        assert response.status_code == 422
        assert "Mixed-currency" in response.json()["detail"]


def test_trial_balance_api_reports_missing_fx_rate() -> None:
    with create_ledger_client() as (client, _engine, organization_id, accounts):
        post_response = client.post(
            "/ledger/post",
            json=_transaction_payload(
                organization_id,
                [
                    {"account_id": accounts["eur_cash"], "debit": 10, "credit": 0},
                    {"account_id": accounts["eur_equity"], "debit": 0, "credit": 10},
                ],
            ),
        )
        assert post_response.status_code == 200

        response = client.get(
            "/ledger/trial-balance",
            params={"organization_id": organization_id, "currency": "USD"},
        )
        assert response.status_code == 422
        assert "Missing FX rate for EUR/USD" in response.json()["detail"]