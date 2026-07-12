"""Integration tests for ledger posting and conversion invariants."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest
from apps.api import db
from apps.api.db import get_session
from apps.api.main import create_app
from apps.api.models.models import Account, JournalEntry, Membership, Organization, Transaction, User
from apps.api.security import create_access_token, get_password_hash
from apps.api.services.ledger_service import LedgerService
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select


@pytest.fixture()
def ledger_api_context() -> Iterator[tuple[TestClient, dict[str, object], object]]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    db.engine = engine
    db.connect_args = {"check_same_thread": False}

    app = create_app()

    def override_get_session() -> Iterator[Session]:
        with Session(engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    client = TestClient(app)

    with Session(engine, expire_on_commit=False) as session:
        organization = Organization(name="Ledger API Org")
        user = User(email="ledger-admin@example.com", password_hash=get_password_hash("secret"))
        session.add_all([organization, user])
        session.commit()
        session.refresh(organization)
        session.refresh(user)

        membership = Membership(
            user_id=user.id,
            organization_id=organization.id,
            is_admin=True,
            can_manage_ledger=True,
            can_manage_tax=True,
        )
        session.add(membership)
        session.commit()

        ledger = LedgerService(session, organization_id=organization.id)
        usd_cash = ledger.create_account("USD Cash", "ASSET", code="USD-CASH", currency="USD")
        usd_revenue = ledger.create_account("USD Revenue", "REVENUE", code="USD-REV", currency="USD")
        eur_receivable = ledger.create_account("EUR Receivable", "ASSET", code="EUR-AR", currency="EUR")
        eur_revenue = ledger.create_account("EUR Revenue", "REVENUE", code="EUR-REV", currency="EUR")
        ledger.post_transaction(
            date=date(2024, 1, 1),
            description="EUR opening activity",
            postings=[
                {"account_id": eur_receivable.id, "debit": 50.0, "credit": 0.0},
                {"account_id": eur_revenue.id, "debit": 0.0, "credit": 50.0},
            ],
        )

        context = {
            "organization_id": organization.id,
            "token": create_access_token({"sub": str(user.id)}),
            "usd_cash_id": usd_cash.id,
            "usd_revenue_id": usd_revenue.id,
            "eur_revenue_id": eur_revenue.id,
        }

    try:
        yield client, context, engine
    finally:
        client.close()
        engine.dispose()


def _headers(context: dict[str, object]) -> dict[str, str]:
    return {"Authorization": f"Bearer {context['token']}"}


def _transaction_count(engine: object) -> tuple[int, int]:
    with Session(engine) as session:
        transactions = len(session.exec(select(Transaction)).all())
        entries = len(session.exec(select(JournalEntry)).all())
    return transactions, entries


def test_empty_postings_return_controlled_client_error(ledger_api_context) -> None:
    client, context, _ = ledger_api_context
    response = client.post(
        "/ledger/post",
        headers=_headers(context),
        json={
            "date": "2024-02-01",
            "description": "Empty transaction",
            "postings": [],
            "organization_id": context["organization_id"],
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "At least two postings are required"


def test_single_posting_is_rejected_by_request_validation(ledger_api_context) -> None:
    client, context, _ = ledger_api_context
    response = client.post(
        "/ledger/post",
        headers=_headers(context),
        json={
            "date": "2024-02-01",
            "description": "Single posting",
            "postings": [
                {"account_id": context["usd_cash_id"], "debit": "10.00", "credit": "0"},
            ],
            "organization_id": context["organization_id"],
        },
    )

    assert response.status_code == 422


def test_missing_account_returns_400_without_partial_persistence(ledger_api_context) -> None:
    client, context, engine = ledger_api_context
    before = _transaction_count(engine)
    response = client.post(
        "/ledger/post",
        headers=_headers(context),
        json={
            "date": "2024-02-01",
            "description": "Missing account",
            "postings": [
                {"account_id": context["usd_cash_id"], "debit": "25.00", "credit": "0"},
                {"account_id": 999999, "debit": "0", "credit": "25.00"},
            ],
            "organization_id": context["organization_id"],
        },
    )

    assert response.status_code == 400
    assert "not found" in response.json()["detail"]
    assert _transaction_count(engine) == before


def test_cross_currency_offset_returns_400_without_partial_persistence(ledger_api_context) -> None:
    client, context, engine = ledger_api_context
    before = _transaction_count(engine)
    response = client.post(
        "/ledger/post",
        headers=_headers(context),
        json={
            "date": "2024-02-01",
            "description": "Cross-currency offset",
            "postings": [
                {"account_id": context["usd_cash_id"], "debit": "100.00", "credit": "0"},
                {"account_id": context["eur_revenue_id"], "debit": "0", "credit": "100.00"},
            ],
            "organization_id": context["organization_id"],
        },
    )

    assert response.status_code == 400
    assert "not balanced for currency" in response.json()["detail"]
    assert _transaction_count(engine) == before


def test_trial_balance_missing_fx_rate_returns_400(ledger_api_context) -> None:
    client, context, _ = ledger_api_context
    response = client.get(
        "/ledger/trial-balance",
        headers=_headers(context),
        params={"organization_id": context["organization_id"], "currency": "USD"},
    )

    assert response.status_code == 400
    assert "Missing FX rate for EUR/USD" in response.json()["detail"]


def test_balanced_same_currency_transaction_remains_supported(ledger_api_context) -> None:
    client, context, _ = ledger_api_context
    response = client.post(
        "/ledger/post",
        headers=_headers(context),
        json={
            "date": "2024-02-01",
            "description": "USD sale",
            "postings": [
                {"account_id": context["usd_cash_id"], "debit": "75.00", "credit": "0"},
                {"account_id": context["usd_revenue_id"], "debit": "0", "credit": "75.00"},
            ],
            "organization_id": context["organization_id"],
        },
    )

    assert response.status_code == 200
    assert response.json()["description"] == "USD sale"


def test_fixture_accounts_are_scoped_to_expected_organization(ledger_api_context) -> None:
    _, context, engine = ledger_api_context
    with Session(engine) as session:
        accounts = session.exec(
            select(Account).where(Account.organization_id == context["organization_id"])
        ).all()
    assert {account.code for account in accounts} == {"USD-CASH", "USD-REV", "EUR-AR", "EUR-REV"}
