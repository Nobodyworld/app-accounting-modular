from __future__ import annotations

from datetime import date
from decimal import Decimal

import apps.api.services.reconciliation_service as reconciliation_module
import pytest
from apps.api.models.models import Budget, BudgetLine, VarianceDisposition, VarianceReview, VarianceReviewRun
from apps.api.services.close_service import CloseConflictError, CloseService, CloseValidationError
from apps.api.services.ledger_service import LedgerService
from apps.api.services.reconciliation_service import ReconciliationService
from sqlmodel import select

from tests._close_helpers import close_session


def test_budget_report_is_reused_for_decimal_materiality_and_disposition() -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id
        close = CloseService(session, actors.organization.id, actors.preparer.id)
        period = close.create_period("January 2027", date(2027, 1, 1), date(2027, 1, 31))
        cycle = close.create_cycle(period.id, "January close")
        cycle = close.start(cycle.id, cycle.version)
        ledger = LedgerService(session, actors.organization.id)
        expense = ledger.create_account("Payroll expense", "EXPENSE", code="6000")
        cash = ledger.create_account("Cash", "ASSET", code="1000")
        ledger.post_transaction(
            date(2027, 1, 15),
            "Payroll",
            [
                {"account_id": expense.id, "debit": 1250, "credit": 0},
                {"account_id": cash.id, "debit": 0, "credit": 1250},
            ],
        )
        budget = Budget(
            organization_id=actors.organization.id,
            name="January budget",
            start_date=date(2027, 1, 1),
            end_date=date(2027, 1, 31),
        )
        session.add(budget)
        session.commit()
        session.refresh(budget)
        budget_line = BudgetLine(
            budget_id=budget.id,
            account_id=expense.id,
            period_start=date(2027, 1, 1),
            amount=1000,
        )
        session.add(budget_line)
        session.commit()
        service = ReconciliationService(session, actors.organization.id, actors.preparer.id)
        reviews = service.materialize_variances(
            cycle.id,
            budget_id=budget.id,
            horizon=30,
            absolute_threshold=Decimal("200"),
            percentage_threshold=Decimal("0.10"),
        )
        assert len(reviews) == 1
        review = reviews[0]
        assert review.variance_amount == Decimal("250.0000")
        assert review.is_material is True
        assert review.report_metadata["budget_id"] == budget.id
        updated = service.update_variance(
            cycle.id,
            review.id,
            version=review.version,
            disposition=VarianceDisposition.EXPLAINED,
            note="One-time payroll catch-up",
        )
        assert updated.reviewed_at is not None

        budget_line.amount = 1250
        session.add(budget_line)
        session.commit()
        current = service.materialize_variances(
            cycle.id,
            budget_id=budget.id,
            horizon=30,
            absolute_threshold=Decimal("1"),
            percentage_threshold=None,
            refresh=True,
        )
        assert len(current) == 1
        assert current[0].run_id != review.run_id
        assert current[0].variance_amount == Decimal("0.0000")
        assert current[0].is_material is False
        assert current[0].disposition == VarianceDisposition.UNRESOLVED
        assert len(session.exec(select(VarianceReviewRun)).all()) == 2
        assert len(session.exec(select(VarianceReview)).all()) == 2
        with pytest.raises(CloseConflictError, match="latest variance"):
            service.update_variance(
                cycle.id,
                review.id,
                version=updated.version,
                disposition=VarianceDisposition.EXPLAINED,
                note="Historical row must remain immutable",
            )


def test_variance_review_row_limit_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reconciliation_module, "MAX_VARIANCE_REVIEW_ROWS", 0)
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id
        close = CloseService(session, actors.organization.id, actors.preparer.id)
        period = close.create_period("February 2027", date(2027, 2, 1), date(2027, 2, 28))
        cycle = close.create_cycle(period.id, "February close")
        close.start(cycle.id, cycle.version)
        expense = LedgerService(session, actors.organization.id).create_account("Expense", "EXPENSE", code="6000")
        budget = Budget(
            organization_id=actors.organization.id,
            name="February budget",
            start_date=date(2027, 2, 1),
            end_date=date(2027, 2, 28),
        )
        session.add(budget)
        session.commit()
        session.refresh(budget)
        session.add(
            BudgetLine(
                budget_id=budget.id,
                account_id=expense.id,
                period_start=date(2027, 2, 1),
                amount=Decimal("100"),
            )
        )
        session.commit()

        with pytest.raises(CloseValidationError, match="maximum variance review rows"):
            ReconciliationService(session, actors.organization.id, actors.preparer.id).materialize_variances(
                cycle.id,
                budget_id=budget.id,
                horizon=30,
                absolute_threshold=Decimal("0"),
                percentage_threshold=None,
            )


def test_variance_pages_have_stable_order_without_gaps() -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id
        close = CloseService(session, actors.organization.id, actors.preparer.id)
        period = close.create_period("March 2027", date(2027, 3, 1), date(2027, 3, 31))
        cycle = close.create_cycle(period.id, "March close")
        close.start(cycle.id, cycle.version)
        ledger = LedgerService(session, actors.organization.id)
        accounts = [ledger.create_account(f"Expense {index}", "EXPENSE", code=f"6{index:03d}") for index in range(4)]
        budget = Budget(
            organization_id=actors.organization.id,
            name="March budget",
            start_date=date(2027, 3, 1),
            end_date=date(2027, 3, 31),
        )
        session.add(budget)
        session.commit()
        session.refresh(budget)
        session.add_all(
            [
                BudgetLine(
                    budget_id=budget.id,
                    account_id=account.id,
                    period_start=date(2027, 3, 1),
                    amount=Decimal(index),
                )
                for index, account in enumerate(reversed(accounts), start=1)
            ]
        )
        session.commit()
        service = ReconciliationService(session, actors.organization.id, actors.preparer.id)
        service.materialize_variances(
            cycle.id,
            budget_id=budget.id,
            horizon=30,
            absolute_threshold=Decimal("0"),
            percentage_threshold=None,
        )

        first = service.list_variances(cycle.id, limit=2, offset=0)
        second = service.list_variances(cycle.id, limit=2, offset=2)
        combined = first + second
        assert [item.account_id for item in combined] == sorted(account.id for account in accounts)
        assert len({item.id for item in combined}) == len(accounts)
