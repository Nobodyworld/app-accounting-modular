"""Budget service unit tests covering reporting and forecasting flows."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine

from apps.api.models.models import (
    Budget,
    BudgetLine,
    ForecastOutput,
    ForecastPlan,
    Organization,
)
from apps.api.services.budget_service import BudgetService
from apps.api.services.ledger_service import LedgerService


def create_session() -> Session:
    """Construct an in-memory SQLModel session for budget service tests."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine, expire_on_commit=False)


def seed_basic_ledger(session: Session) -> tuple[int, int]:
    """Populate ledger activity and budget scaffolding for downstream tests."""
    org = Organization(name="Test Org")
    session.add(org)
    session.commit()
    session.refresh(org)

    ledger = LedgerService(session)
    cash = ledger.create_account("Cash", "ASSET", code="1000", organization_id=org.id)
    expense = ledger.create_account("Marketing", "EXPENSE", code="5000", organization_id=org.id)

    ledger.post_transaction(
        date=date(2024, 1, 10),
        description="Launch campaign",
        postings=[
            {"account_id": expense.id, "debit": 600.0, "credit": 0.0},
            {"account_id": cash.id, "debit": 0.0, "credit": 600.0},
        ],
    )
    ledger.post_transaction(
        date=date(2024, 2, 5),
        description="Ad spend",
        postings=[
            {"account_id": expense.id, "debit": 450.0, "credit": 0.0},
            {"account_id": cash.id, "debit": 0.0, "credit": 450.0},
        ],
    )

    budget = Budget(
        organization_id=org.id,
        name="FY24 Marketing",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        currency="USD",
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
                amount=500.0,
            ),
            BudgetLine(
                budget_id=budget.id,
                account_id=expense.id,
                period_start=date(2024, 2, 1),
                amount=400.0,
            ),
        ]
    )
    session.commit()
    return org.id, budget.id


def test_budget_vs_actual_generates_and_persists() -> None:
    with create_session() as session:
        org_id, budget_id = seed_basic_ledger(session)
        service = BudgetService(session)

        report = service.budget_vs_actual(budget_id, horizon=30, refresh=True)

        assert report.lines
        assert pytest.approx(report.total_actual, rel=1e-3) == 1050.0
        assert report.metadata["budget_id"] == budget_id

        outputs = session.exec(select(func.count()).select_from(ForecastOutput)).one()[0]
        assert outputs == 1

        cached = service.budget_vs_actual(budget_id)
        assert cached.csv_export == report.csv_export


def test_cashflow_forecast_handles_history() -> None:
    with create_session() as session:
        org_id, budget_id = seed_basic_ledger(session)
        service = BudgetService(session)

        report = service.cashflow_forecast(org_id, horizon=15, refresh=True)

        assert report.historical
        assert report.metadata["organization_id"] == org_id
        cashflow_outputs = session.exec(
            select(func.count()).select_from(ForecastOutput).where(ForecastOutput.report_type == "cashflow_forecast")
        ).one()[0]
        assert cashflow_outputs == 1

    # TODO - (budget) Extend coverage to include stress tests for seasonal projections.


def test_budget_vs_actual_requires_budget() -> None:
    with create_session() as session:
        service = BudgetService(session)
        with pytest.raises(ValueError):
            service.budget_vs_actual(999)


def test_cashflow_forecast_records_error_diagnostics() -> None:
    class FailingForecastService:
        def forecast_series(self, *args, **kwargs):
            raise ValueError("model failed")

    with create_session() as session:
        org_id, _ = seed_basic_ledger(session)
        service = BudgetService(session, forecast_service=FailingForecastService())

        report = service.cashflow_forecast(org_id, horizon=5, refresh=True)
        assert report.metadata["forecast_status"] == "error"
        diagnostics = report.metadata.get("forecast_diagnostics")
        assert diagnostics and diagnostics.get("detail") == "model failed"


def test_budget_plan_creation_handles_race(monkeypatch) -> None:
    with create_session() as session:
        org_id, budget_id = seed_basic_ledger(session)
        service = BudgetService(session)

        original_commit = session.commit
        race_triggered = {"count": 0}

        def racing_commit() -> None:
            if race_triggered["count"] == 0:
                race_triggered["count"] += 1
                with Session(session.get_bind(), expire_on_commit=False) as competitor:
                    plan = ForecastPlan(
                        organization_id=org_id,
                        budget_id=budget_id,
                        name=BudgetService.BUDGET_PLAN_NAME,
                        horizon=90,
                    )
                    competitor.add(plan)
                    competitor.commit()
                raise IntegrityError("duplicate", params=None, orig=Exception())
            original_commit()

        monkeypatch.setattr(session, "commit", racing_commit)
        plan = service._ensure_budget_plan(budget_id, horizon=None)

        assert plan.id is not None
        count = session.exec(select(func.count()).select_from(ForecastPlan)).one()[0]
        assert count == 1
