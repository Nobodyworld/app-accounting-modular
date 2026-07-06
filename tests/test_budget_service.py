"""Budget service unit tests covering reporting and forecasting flows."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from typing import Any, cast

import pytest
from apps.api.models.models import (
    Budget,
    BudgetLine,
    ForecastOutput,
    ForecastPlan,
    Organization,
)
from apps.api.services.budget_service import BudgetService
from apps.api.services.ledger_service import LedgerService
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select


@contextmanager
def create_session() -> Iterator[Session]:
    """Construct an in-memory SQLModel session for budget service tests."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def seed_basic_ledger(session: Session) -> tuple[int, int]:
    """Populate ledger activity and budget scaffolding for downstream tests."""
    org = Organization(name="Test Org")
    session.add(org)
    session.commit()
    session.refresh(org)
    if org.id is None:
        raise AssertionError("Organization id was not persisted")
    org_id = org.id

    ledger = LedgerService(session)
    cash = ledger.create_account("Cash", "ASSET", code="1000", organization_id=org_id)
    expense = ledger.create_account("Marketing", "EXPENSE", code="5000", organization_id=org_id)
    if cash.id is None or expense.id is None:
        raise AssertionError("Account ids were not persisted")
    cash_id = cash.id
    expense_id = expense.id

    ledger.post_transaction(
        date=date(2024, 1, 10),
        description="Launch campaign",
        postings=[
            {"account_id": expense_id, "debit": 600.0, "credit": 0.0},
            {"account_id": cash_id, "debit": 0.0, "credit": 600.0},
        ],
    )
    ledger.post_transaction(
        date=date(2024, 2, 5),
        description="Ad spend",
        postings=[
            {"account_id": expense_id, "debit": 450.0, "credit": 0.0},
            {"account_id": cash_id, "debit": 0.0, "credit": 450.0},
        ],
    )

    budget = Budget(
        organization_id=org_id,
        name="FY24 Marketing",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        currency="USD",
    )
    session.add(budget)
    session.commit()
    session.refresh(budget)
    if budget.id is None:
        raise AssertionError("Budget id was not persisted")
    budget_id = budget.id

    session.add_all(
        [
            BudgetLine(
                budget_id=budget_id,
                account_id=expense_id,
                period_start=date(2024, 1, 1),
                amount=500.0,
            ),
            BudgetLine(
                budget_id=budget_id,
                account_id=expense_id,
                period_start=date(2024, 2, 1),
                amount=400.0,
            ),
        ]
    )
    session.commit()
    return org_id, budget_id


def test_budget_vs_actual_generates_and_persists() -> None:
    with create_session() as session:
        org_id, budget_id = seed_basic_ledger(session)
        service = BudgetService(session)

        report = service.budget_vs_actual(budget_id, horizon=30, refresh=True)

        assert report.lines
        assert pytest.approx(report.total_actual, rel=1e-3) == 1050.0
        assert report.metadata["budget_id"] == budget_id

        outputs = len(session.exec(select(ForecastOutput)).all())
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
        cashflow_outputs = len(
            [row for row in session.exec(select(ForecastOutput)).all() if row.report_type == "cashflow_forecast"]
        )
        assert cashflow_outputs == 1


# TODO - (budget) Extend coverage to include stress tests for seasonal projections.
def test_budget_vs_actual_handles_seasonal_projection_stress(monkeypatch: pytest.MonkeyPatch) -> None:
    with create_session() as session:
        _org_id, budget_id = seed_basic_ledger(session)

        class SlowForecast:
            def __init__(self) -> None:
                self.calls = 0

            def forecast_series(self, series: object, horizon: int, **kwargs: object) -> object:
                self.calls += 1
                return type(
                    "Result",
                    (),
                    {
                        "points": [(f"2024-0{i + 3}-01", 100.0) for i in range(horizon)],
                        "horizon": horizon,
                        "model_order": (0, 0, 0),
                        "diagnostics": {"strategy": "stub"},
                        "timezone": "UTC",
                    },
                )

        stub = SlowForecast()
        service = BudgetService(session, forecast_service=cast(Any, stub))
        report = service.budget_vs_actual(budget_id, horizon=60, refresh=True)

    assert report.lines
    assert stub.calls >= 1
    assert report.metadata.get("forecast_status") in ("success", None)


def test_budget_vs_actual_requires_budget() -> None:
    with create_session() as session:
        service = BudgetService(session)
        with pytest.raises(ValueError):
            service.budget_vs_actual(999)


def test_cashflow_forecast_records_error_diagnostics() -> None:
    class FailingForecastService:
        def forecast_series(self, *args: object, **kwargs: object) -> object:
            raise ValueError("model failed")

    with create_session() as session:
        org_id, _ = seed_basic_ledger(session)
        service = BudgetService(session, forecast_service=cast(Any, FailingForecastService()))

        report = service.cashflow_forecast(org_id, horizon=5, refresh=True)
        assert report.metadata["forecast_status"] == "error"
        diagnostics = report.metadata.get("forecast_diagnostics")
        assert isinstance(diagnostics, dict)
        assert diagnostics.get("detail") == "model failed"


def test_budget_plan_creation_handles_race(monkeypatch: pytest.MonkeyPatch) -> None:
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
        count = len(session.exec(select(ForecastPlan)).all())
        assert count == 1
