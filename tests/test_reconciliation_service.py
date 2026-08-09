from __future__ import annotations

from datetime import date
from decimal import Decimal

import apps.api.services.reconciliation_service as reconciliation_module
import pytest
from apps.api.models.models import ReconciliationStatus, VarianceDisposition
from apps.api.services.close_service import CloseConflictError, CloseNotFoundError, CloseService, CloseValidationError
from apps.api.services.ledger_service import LedgerService
from apps.api.services.reconciliation_service import ReconciliationService

from tests._close_helpers import close_session


def test_reconciliation_sign_tolerance_and_independent_approval() -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id and actors.reviewer.id
        close = CloseService(session, actors.organization.id, actors.preparer.id)
        period = close.create_period("August 2026", date(2026, 8, 1), date(2026, 8, 31))
        cycle = close.create_cycle(period.id, "August close")
        close.start(cycle.id, cycle.version)
        ledger = LedgerService(session, actors.organization.id)
        cash = ledger.create_account("Cash", "ASSET", code="1000")
        revenue = ledger.create_account("Revenue", "REVENUE", code="4000")
        ledger.post_transaction(
            date(2026, 8, 10),
            "August sale",
            [
                {"account_id": cash.id, "debit": 100, "credit": 0},
                {"account_id": revenue.id, "debit": 0, "credit": 100},
            ],
        )
        preparer = ReconciliationService(session, actors.organization.id, actors.preparer.id)
        reconciliation = preparer.prepare_reconciliation(
            cycle.id,
            cash.id,
            control_balance=Decimal("100.01"),
            tolerance=Decimal("0.01"),
        )
        assert reconciliation.ledger_ending_balance == Decimal("100.0000")
        assert reconciliation.difference == Decimal("0.0100")
        assert reconciliation.status == ReconciliationStatus.MATCHED
        with pytest.raises(CloseConflictError, match="preparer"):
            preparer.approve_reconciliation(cycle.id, reconciliation.id, version=reconciliation.version)
        reviewer = ReconciliationService(session, actors.organization.id, actors.reviewer.id)
        approved = reviewer.approve_reconciliation(cycle.id, reconciliation.id, version=reconciliation.version)
        assert approved.status == ReconciliationStatus.APPROVED
        assert approved.approved_by_id == actors.reviewer.id


def test_exception_becomes_in_progress_only_with_documented_note() -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id
        close = CloseService(session, actors.organization.id, actors.preparer.id)
        period = close.create_period("September 2026", date(2026, 9, 1), date(2026, 9, 30))
        cycle = close.create_cycle(period.id, "September close")
        cycle = close.start(cycle.id, cycle.version)
        account = LedgerService(session, actors.organization.id).create_account("Cash", "ASSET", code="1000")
        service = ReconciliationService(session, actors.organization.id, actors.preparer.id)
        exception = service.prepare_reconciliation(
            cycle.id, account.id, control_balance=Decimal("10"), tolerance=Decimal("0")
        )
        assert exception.status == ReconciliationStatus.EXCEPTION
        documented = service.prepare_reconciliation(
            cycle.id,
            account.id,
            control_balance=Decimal("10"),
            tolerance=Decimal("0"),
            notes="Outstanding deposit under investigation",
            version=exception.version,
        )
        assert documented.status == ReconciliationStatus.IN_PROGRESS


def test_reconciliation_validation_and_missing_reference_paths() -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id and actors.reviewer.id
        close = CloseService(session, actors.organization.id, actors.preparer.id)
        period = close.create_period("October 2026", date(2026, 10, 1), date(2026, 10, 31))
        cycle = close.create_cycle(period.id, "October close")
        cycle = close.start(cycle.id, cycle.version)
        account = LedgerService(session, actors.organization.id).create_account("Cash", "ASSET", code="1000")
        service = ReconciliationService(session, actors.organization.id, actors.preparer.id)

        with pytest.raises(CloseNotFoundError, match="Account"):
            service.ledger_ending_balance(cycle.id, 999_999)
        with pytest.raises(CloseValidationError, match="nonnegative"):
            service.prepare_reconciliation(cycle.id, account.id, control_balance=None, tolerance=Decimal("-1"))
        unstarted = service.prepare_reconciliation(cycle.id, account.id, control_balance=None, tolerance=Decimal("0"))
        assert unstarted.status == ReconciliationStatus.UNSTARTED
        with pytest.raises(CloseConflictError, match="stale"):
            service.prepare_reconciliation(
                cycle.id,
                account.id,
                control_balance=Decimal("0"),
                tolerance=Decimal("0"),
                version=999,
            )
        reviewer = ReconciliationService(session, actors.organization.id, actors.reviewer.id)
        with pytest.raises(CloseNotFoundError, match="Reconciliation"):
            reviewer.approve_reconciliation(cycle.id, 999_999, version=1)
        with pytest.raises(CloseConflictError, match="stale"):
            reviewer.approve_reconciliation(cycle.id, unstarted.id, version=999)
        with pytest.raises(CloseConflictError, match="matched or documented"):
            reviewer.approve_reconciliation(cycle.id, unstarted.id, version=unstarted.version)
        with pytest.raises(CloseNotFoundError, match="Budget"):
            service.materialize_variances(
                cycle.id,
                budget_id=999_999,
                horizon=30,
                absolute_threshold=Decimal("0"),
                percentage_threshold=None,
            )
        with pytest.raises(CloseNotFoundError, match="Variance"):
            service.update_variance(
                cycle.id,
                999_999,
                version=1,
                disposition=VarianceDisposition.EXPLAINED,
                note="Reviewed",
            )
        with pytest.raises(CloseValidationError, match="Exactly one"):
            service.request_approval(cycle.id)
        with pytest.raises(CloseNotFoundError, match="Journal transaction"):
            service.request_approval(cycle.id, transaction_id=999_999)
        with pytest.raises(CloseNotFoundError, match="Staged transaction"):
            service.request_approval(cycle.id, staged_transaction_id=999_999)


def test_reconciliation_limit_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reconciliation_module, "MAX_RECONCILIATIONS_PER_CYCLE", 1)
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id
        close = CloseService(session, actors.organization.id, actors.preparer.id)
        period = close.create_period("November 2026", date(2026, 11, 1), date(2026, 11, 30))
        cycle = close.create_cycle(period.id, "November close")
        close.start(cycle.id, cycle.version)
        ledger = LedgerService(session, actors.organization.id)
        cash = ledger.create_account("Cash", "ASSET", code="1000")
        receivable = ledger.create_account("Receivable", "ASSET", code="1100")
        service = ReconciliationService(session, actors.organization.id, actors.preparer.id)

        service.prepare_reconciliation(cycle.id, cash.id, control_balance=None, tolerance=Decimal("0"))
        with pytest.raises(CloseValidationError, match="Maximum reconciliations"):
            service.prepare_reconciliation(
                cycle.id,
                receivable.id,
                control_balance=None,
                tolerance=Decimal("0"),
            )


def test_reconciliation_pages_have_stable_order_without_gaps() -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id
        close = CloseService(session, actors.organization.id, actors.preparer.id)
        period = close.create_period("December 2026", date(2026, 12, 1), date(2026, 12, 31))
        cycle = close.create_cycle(period.id, "December close")
        close.start(cycle.id, cycle.version)
        ledger = LedgerService(session, actors.organization.id)
        accounts = [ledger.create_account(f"Account {index}", "ASSET", code=f"1{index:03d}") for index in range(5)]
        service = ReconciliationService(session, actors.organization.id, actors.preparer.id)
        for account in reversed(accounts):
            service.prepare_reconciliation(cycle.id, account.id, control_balance=None, tolerance=Decimal("0"))

        first = service.list_reconciliations(cycle.id, limit=2, offset=0)
        second = service.list_reconciliations(cycle.id, limit=2, offset=2)
        third = service.list_reconciliations(cycle.id, limit=2, offset=4)
        combined = first + second + third
        assert [item.account_id for item in combined] == sorted(account.id for account in accounts)
        assert len({item.id for item in combined}) == len(accounts)
