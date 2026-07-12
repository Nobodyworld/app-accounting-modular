"""Tests covering reporting router endpoints and helper formatting routines."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from apps.api import db
from apps.api.models.models import Budget, BudgetLine, ForecastOutput, Organization, Rate
from apps.api.routers.reports import (
    _response_from_cashflow,
    budget_vs_actual,
    cashflow_forecast,
)
from apps.api.services.budget_service import CashflowReport
from apps.api.services.forecast_service import ForecastResult
from apps.api.services.ledger_service import LedgerService
from apps.api.utils.metadata import prepare_metadata_for_response
from fastapi import HTTPException
from sqlalchemy import select
from sqlmodel import Session, SQLModel, create_engine


@contextmanager
def setup_database() -> Iterator[Session]:
    """Initialise the in-memory database and bind the global engine for tests."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    db.engine = engine
    SQLModel.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def seed_data(session: Session) -> tuple[int, int]:
    """Populate base ledger and budgeting fixtures for report assertions."""
    org = Organization(name="API Org")
    session.add(org)
    session.commit()
    session.refresh(org)

    ledger = LedgerService(session)
    cash = ledger.create_account("Cash", "ASSET", code="1000", organization_id=org.id)
    expense = ledger.create_account(
        "Ops",
        "EXPENSE",
        code="5000",
        organization_id=org.id,
    )
    shadow_expense = ledger.create_account("Backoffice", "EXPENSE", code="5100", organization_id=org.id)

    ledger.post_transaction(
        date=date(2024, 1, 1),
        description="Ops Spend",
        postings=[
            {"account_id": expense.id, "debit": 300.0, "credit": 0.0},
            {"account_id": cash.id, "debit": 0.0, "credit": 300.0},
        ],
    )
    ledger.post_transaction(
        date=date(2024, 2, 1),
        description="Ops Spend",
        postings=[
            {"account_id": expense.id, "debit": 275.0, "credit": 0.0},
            {"account_id": cash.id, "debit": 0.0, "credit": 275.0},
        ],
    )

    budget = Budget(
        organization_id=org.id,
        name="Ops 2024",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )
    session.add(budget)
    session.commit()
    session.refresh(budget)

    session.add_all(
        [
            BudgetLine(
                budget_id=budget.id,
                account_id=expense.id,
                period_start=date(2024, 1, 1),
                amount=280.0,
            ),
            BudgetLine(
                budget_id=budget.id,
                account_id=expense.id,
                period_start=date(2024, 2, 1),
                amount=300.0,
            ),
            BudgetLine(
                budget_id=budget.id,
                account_id=shadow_expense.id,
                period_start=date(2024, 1, 1),
                amount=150.0,
            ),
        ]
    )
    session.commit()
    return org.id, budget.id


def test_budget_vs_actual_multicurrency_conversion() -> None:
    with setup_database() as session:
        org = Organization(name="FX Org")
        session.add(org)
        session.commit()
        session.refresh(org)

        ledger = LedgerService(session)
        eur_payable = ledger.create_account(
            "EUR Payable",
            "LIABILITY",
            code="2000",
            organization_id=org.id,
            currency="EUR",
        )
        expense = ledger.create_account("Ops EUR", "EXPENSE", code="5000", organization_id=org.id, currency="EUR")

        ledger.post_transaction(
            date=date(2024, 1, 1),
            description="EUR spend",
            postings=[
                {"account_id": expense.id, "debit": 100.0, "credit": 0.0, "currency": "EUR"},
                {"account_id": eur_payable.id, "debit": 0.0, "credit": 100.0, "currency": "EUR"},
            ],
        )

        budget = Budget(
            organization_id=org.id,
            name="FX Budget",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            currency="USD",
        )
        session.add(budget)
        session.commit()
        session.refresh(budget)
        session.add(
            BudgetLine(
                budget_id=budget.id,
                account_id=expense.id,
                period_start=date(2024, 1, 1),
                amount=110.0,
            )
        )
        session.commit()
        session.add(Rate(base="EUR", quote="USD", date=date(2024, 1, 1), value=1.1, provider="stub"))
        session.commit()

        response = budget_vs_actual(
            budget_id=budget.id,
            organization_id=org.id,
            horizon=15,
            refresh=True,
            session=session,
        )
        assert response.metadata.reporting_currency == "USD"
        assert response.summary["total_actual"] >= 100.0


def test_budget_vs_actual_endpoint() -> None:
    with setup_database() as session:
        org_id, budget_id = seed_data(session)

        response = budget_vs_actual(
            budget_id=budget_id,
            organization_id=org_id,
            horizon=15,
            refresh=True,
            session=session,
        )
        assert response.summary["total_actual"] > 0
        assert response.metadata.budget_id == budget_id
        assert response.metadata.organization_id == org_id
        assert response.metadata.reporting_currency == "USD"
        assert response.metadata.plan_revision is not None
        assert response.metadata.generated_at.tzinfo == UTC
        assert response.metadata.accounts_without_actuals is not None
        missing = response.metadata.accounts_without_actuals
        assert missing and missing[0].account_name == "Backoffice"

        stored_row = session.exec(
            select(ForecastOutput).where(ForecastOutput.report_type == "budget_vs_actual")
        ).first()
        assert stored_row is not None
        stored = stored_row if isinstance(stored_row, ForecastOutput) else stored_row[0]
        assert stored.plan_id is not None


def test_cashflow_endpoint() -> None:
    with setup_database() as session:
        org_id, budget_id = seed_data(session)

        response = cashflow_forecast(
            organization_id=org_id,
            horizon=10,
            refresh=True,
            session=session,
        )
        assert response.metadata.organization_id == org_id
        assert response.current_cash < 0
        assert response.metadata.forecast_diagnostics is not None
        diagnostics = response.metadata.forecast_diagnostics
        assert diagnostics is not None
        assert isinstance(diagnostics.get("last_observation_label"), str)
        assert response.metadata.forecast_status == "success"
        assert response.metadata.forecast_timezone == "UTC"


def test_prepare_metadata_for_response_serialises_diagnostics() -> None:
    raw = {
        "forecast_diagnostics": {
            "last_observation_label": "2024-03-01T00:00:00+00:00",
            "observations": 10,
            "baseline_value": Decimal("12.5"),
            "flag": True,
            "detail": None,
        }
    }

    normalised = prepare_metadata_for_response(raw)

    diagnostics = normalised["forecast_diagnostics"]
    assert diagnostics["last_observation_label"] == "2024-03-01T00:00:00+00:00"
    assert diagnostics["observations"] == 10
    assert diagnostics["baseline_value"] == 12.5
    assert diagnostics["flag"] is True
    assert "detail" not in diagnostics


def test_response_from_cashflow_serialises_forecast_diagnostics() -> None:
    forecast = ForecastResult(
        horizon=3,
        points=[("2024-01", 1.0)],
        model_order=(1, 1, 1),
        diagnostics={
            "observations": 4,
            "baseline": Decimal("2.50"),
            "generated_at": datetime(2024, 3, 1, tzinfo=UTC),
            "notes": None,
        },
        timezone="UTC",
    )
    report = CashflowReport(
        historical=[],
        forecast=forecast,
        current_cash=0.0,
        average_monthly_flow=None,
        metadata={
            "generated_at": datetime(2024, 3, 1, tzinfo=UTC),
            "forecast_status": "success",
            "forecast_diagnostics": {"existing": "cached", "baseline": 1.0},
        },
        csv_export="",
    )

    response = _response_from_cashflow(report)

    diagnostics = response.metadata.forecast_diagnostics
    assert diagnostics == {
        "existing": "cached",
        "observations": 4,
        "baseline": 2.5,
        "generated_at": "2024-03-01T00:00:00+00:00",
    }


def test_budget_vs_actual_rejects_cross_org_access() -> None:
    with setup_database() as session:
        org_id, budget_id = seed_data(session)

        with pytest.raises(HTTPException) as excinfo:
            budget_vs_actual(
                budget_id=budget_id,
                organization_id=org_id + 1,
                session=session,
            )

        assert excinfo.value.status_code == 404


def test_budget_vs_actual_returns_400_for_empty_budget() -> None:
    with setup_database() as session:
        org = Organization(name="Empty Budget Org")
        session.add(org)
        session.commit()
        session.refresh(org)

        budget = Budget(
            organization_id=org.id,
            name="Empty",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
        )
        session.add(budget)
        session.commit()
        session.refresh(budget)

        with pytest.raises(HTTPException) as excinfo:
            budget_vs_actual(
                budget_id=budget.id,
                organization_id=org.id,
                session=session,
            )

        assert excinfo.value.status_code == 400


def test_cashflow_forecast_returns_404_for_missing_org() -> None:
    with setup_database() as session:
        with pytest.raises(HTTPException) as excinfo:
            cashflow_forecast(
                organization_id=999,
                session=session,
            )

        assert excinfo.value.status_code == 404
