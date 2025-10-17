from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlmodel import Session, SQLModel, create_engine

from apps.api import db
from apps.api.models.models import Budget, BudgetLine, ForecastOutput, Organization
from apps.api.routers.reports import budget_vs_actual, cashflow_forecast
from apps.api.services.ledger_service import LedgerService


def setup_database() -> Session:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    db.engine = engine
    SQLModel.metadata.create_all(engine)
    return Session(engine, expire_on_commit=False)


def seed_data(session: Session) -> tuple[int, int]:
    org = Organization(name="API Org")
    session.add(org)
    session.commit()
    session.refresh(org)

    ledger = LedgerService(session)
    cash = ledger.create_account("Cash", "ASSET", code="1000", organization_id=org.id)
    expense = ledger.create_account("Ops", "EXPENSE", code="5000", organization_id=org.id)

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
        ]
    )
    session.commit()
    return org.id, budget.id


def test_budget_vs_actual_endpoint() -> None:
    session = setup_database()
    org_id, budget_id = seed_data(session)

    response = budget_vs_actual(budget_id=budget_id, horizon=15, refresh=True, session=session)
    assert response.summary["total_actual"] > 0
    assert response.metadata.budget_id == budget_id

    stored_row = session.exec(select(ForecastOutput).where(ForecastOutput.report_type == "budget_vs_actual")).first()
    assert stored_row is not None
    stored = stored_row if isinstance(stored_row, ForecastOutput) else stored_row[0]
    assert stored.plan_id is not None

    session.close()


def test_cashflow_endpoint() -> None:
    session = setup_database()
    org_id, budget_id = seed_data(session)

    response = cashflow_forecast(
        organization_id=org_id,
        horizon=10,
        refresh=True,
        session=session,
    )
    assert response.metadata.organization_id == org_id
    assert response.current_cash < 0  # cash reduced by spend

    session.close()

