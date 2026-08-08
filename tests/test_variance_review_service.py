from __future__ import annotations

from datetime import date
from decimal import Decimal

from apps.api.models.models import Budget, BudgetLine, VarianceDisposition
from apps.api.services.close_service import CloseService
from apps.api.services.ledger_service import LedgerService
from apps.api.services.reconciliation_service import ReconciliationService

from tests._close_helpers import close_session


def test_budget_report_is_reused_for_decimal_materiality_and_disposition() -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id
        close = CloseService(session, actors.organization.id, actors.preparer.id)
        period = close.create_period("January 2027", date(2027, 1, 1), date(2027, 1, 31))
        cycle = close.create_cycle(period.id, "January close")
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
        session.add(BudgetLine(budget_id=budget.id, account_id=expense.id, period_start=date(2027, 1, 1), amount=1000))
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
