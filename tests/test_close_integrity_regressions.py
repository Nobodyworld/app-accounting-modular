from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from io import BytesIO
from zipfile import ZipFile

import pytest
from apps.api.models.models import (
    AccountingPeriod,
    AccountingPeriodStatus,
    AccountReconciliation,
    AuditLog,
    Budget,
    BudgetLine,
    CloseCycle,
    CloseCycleStatus,
    CloseEvidence,
    CloseTaskControlType,
    JournalApprovalDecision,
    JournalApprovalStatus,
    Membership,
    Organization,
    User,
    VarianceDisposition,
    VarianceReview,
    VarianceReviewRun,
)
from apps.api.services.close_evidence_service import CloseEvidenceService
from apps.api.services.close_service import (
    CloseConflictError,
    CloseNotFoundError,
    CloseService,
    CloseValidationError,
)
from apps.api.services.ledger_service import LedgerService
from apps.api.services.reconciliation_service import ReconciliationService
from sqlmodel import Session, SQLModel, create_engine, select

from tests._close_helpers import close_session


def test_cancelled_cycle_is_immutable_and_restart_preserves_period_and_evidence() -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id and actors.administrator.id
        preparer = CloseService(session, actors.organization.id, actors.preparer.id)
        administrator = CloseService(session, actors.organization.id, actors.administrator.id)
        period = preparer.create_period("Restartable period", date(2028, 1, 1), date(2028, 1, 31))
        cycle = preparer.create_cycle(period.id, "Restartable close", policy={"variance_review_required": False})
        evidence = CloseEvidenceService(session, actors.organization.id, actors.preparer.id)
        evidence.record_generation(cycle.id, evidence.build_bundle(cycle.id))
        original_evidence_id = session.exec(select(CloseEvidence.id)).one()
        original_revision = cycle.content_revision

        with pytest.raises(CloseConflictError, match="administrator"):
            preparer.cancel(cycle.id, cycle.version, "not authorized")
        cancelled = administrator.cancel(cycle.id, cycle.version, "Close deferred")
        assert cancelled.status == CloseCycleStatus.CANCELLED
        assert cancelled.content_revision == original_revision + 1
        assert administrator.require_period(period.id).status == AccountingPeriodStatus.OPEN
        assert evidence.preview(cycle.id)["freshness"] == "STALE"
        with pytest.raises(CloseConflictError, match="CANCELLED"):
            preparer.create_custom_task(cycle.id, title="Must not mutate")
        assert session.exec(select(CloseEvidence.id)).one() == original_evidence_id

        cancelled_revision = cancelled.content_revision
        with pytest.raises(ValueError, match="nonempty"):
            administrator.restart(cycle.id, cancelled.version, " ")
        restarted = administrator.restart(cycle.id, cancelled.version, "Work resumed")
        assert restarted.status == CloseCycleStatus.IN_PROGRESS
        assert restarted.cancelled_at is None
        assert restarted.content_revision == cancelled_revision + 1
        assert session.exec(select(CloseEvidence.id)).one() == original_evidence_id


def test_wrong_reconciliation_path_is_zero_mutation() -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id
        close = CloseService(session, actors.organization.id, actors.preparer.id)
        ledger = LedgerService(session, actors.organization.id)
        account = ledger.create_account("Cash", "ASSET", code="1000")
        period = close.create_period("Path scope", date(2028, 2, 1), date(2028, 2, 29))
        cycle = close.create_cycle(period.id, "Path scoped close", policy={"variance_review_required": False})
        cycle = close.start(cycle.id, cycle.version)
        reconciliations = ReconciliationService(session, actors.organization.id, actors.preparer.id)
        row = reconciliations.prepare_reconciliation(
            cycle.id,
            account.id,
            control_balance=Decimal("0"),
            tolerance=Decimal("0"),
        )
        before = {
            "rows": len(session.exec(select(AccountReconciliation)).all()),
            "version": row.version,
            "revision": close.require_cycle(cycle.id).content_revision,
            "audits": len(session.exec(select(AuditLog)).all()),
        }
        with pytest.raises(CloseNotFoundError, match="Reconciliation"):
            reconciliations.update_reconciliation(
                cycle.id,
                999_999,
                account_id=account.id,
                control_balance=Decimal("10"),
                tolerance=Decimal("0"),
                version=row.version,
            )
        session.refresh(row)
        after = {
            "rows": len(session.exec(select(AccountReconciliation)).all()),
            "version": row.version,
            "revision": close.require_cycle(cycle.id).content_revision,
            "audits": len(session.exec(select(AuditLog)).all()),
        }
        assert after == before


@pytest.mark.parametrize(
    ("open_start", "open_end"),
    [
        (date(2028, 6, 1), date(2028, 6, 10)),
        (date(2028, 6, 20), date(2028, 6, 30)),
        (date(2028, 6, 1), date(2028, 6, 30)),
        (date(2028, 6, 12), date(2028, 6, 18)),
    ],
)
def test_reopen_rejects_every_inclusive_overlap_without_mutation(open_start: date, open_end: date) -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.administrator.id
        service = CloseService(session, actors.organization.id, actors.administrator.id)
        target = AccountingPeriod(
            organization_id=actors.organization.id,
            label="Closed target",
            start_date=date(2028, 6, 10),
            end_date=date(2028, 6, 20),
            status=AccountingPeriodStatus.CLOSED,
        )
        conflict = AccountingPeriod(
            organization_id=actors.organization.id,
            label=f"Conflict {open_start} {open_end}",
            start_date=open_start,
            end_date=open_end,
            status=AccountingPeriodStatus.OPEN,
        )
        session.add_all([target, conflict])
        session.commit()
        session.refresh(target)
        cycle = CloseCycle(
            organization_id=actors.organization.id,
            period_id=target.id,
            name="Closed cycle",
            status=CloseCycleStatus.CLOSED,
            owner_user_id=actors.administrator.id,
        )
        session.add(cycle)
        session.commit()
        session.refresh(cycle)
        before_audits = len(session.exec(select(AuditLog)).all())
        with pytest.raises(CloseConflictError, match="overlaps"):
            service.reopen(cycle.id, cycle.version, "Adjustment")
        session.refresh(cycle)
        session.refresh(target)
        assert cycle.status == CloseCycleStatus.CLOSED
        assert cycle.version == 1
        assert cycle.content_revision == 1
        assert target.status == AccountingPeriodStatus.CLOSED
        assert target.version == 1
        assert len(session.exec(select(AuditLog)).all()) == before_audits


def test_rejected_approval_can_be_rerequested_and_independently_approved() -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id and actors.reviewer.id and actors.administrator.id
        close = CloseService(session, actors.organization.id, actors.preparer.id)
        period = close.create_period("Approval lifecycle", date(2028, 3, 1), date(2028, 3, 31))
        cycle = close.create_cycle(period.id, "Approval close", policy={"variance_review_required": False})
        cycle = close.start(cycle.id, cycle.version)
        ledger = LedgerService(session, actors.organization.id)
        cash = ledger.create_account("Cash", "ASSET", code="1000")
        revenue = ledger.create_account("Revenue", "REVENUE", code="4000")
        transaction = ledger.post_transaction(
            date(2028, 3, 10),
            "Approval journal",
            [
                {"account_id": cash.id, "debit": 10, "credit": 0},
                {"account_id": revenue.id, "debit": 0, "credit": 10},
            ],
        )
        requestor = ReconciliationService(session, actors.organization.id, actors.preparer.id)
        reviewer = ReconciliationService(session, actors.organization.id, actors.reviewer.id)
        approval = requestor.request_approval(cycle.id, transaction_id=transaction.id)
        rejected = reviewer.decide_approval(
            cycle.id,
            approval.id,
            version=approval.version,
            decision=JournalApprovalStatus.REJECTED,
            reason="Supporting detail required",
        )
        rerequested = requestor.request_approval(
            cycle.id,
            transaction_id=transaction.id,
            reason="Supporting detail attached",
        )
        assert rerequested.id == rejected.id
        approved = reviewer.decide_approval(
            cycle.id,
            rerequested.id,
            version=rerequested.version,
            decision=JournalApprovalStatus.APPROVED,
            reason="Reviewed",
        )
        assert approved.status == JournalApprovalStatus.APPROVED
        history = reviewer.approval_history(approved.id)
        assert [item.to_status for item in history] == [
            JournalApprovalStatus.REJECTED,
            JournalApprovalStatus.REQUESTED,
            JournalApprovalStatus.APPROVED,
        ]
        assert session.exec(select(JournalApprovalDecision)).all() == history
        assert not any(blocker.code == "JOURNAL_APPROVALS_INCOMPLETE" for blocker in close.readiness(cycle.id).blockers)


def test_variance_run_is_period_scoped_and_zero_rows_still_prove_execution() -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id
        close = CloseService(session, actors.organization.id, actors.preparer.id)
        ledger = LedgerService(session, actors.organization.id)
        expense = ledger.create_account("Expense", "EXPENSE", code="6000")
        period = close.create_period("April variance", date(2028, 4, 1), date(2028, 4, 30))
        cycle = close.create_cycle(period.id, "April close")
        cycle = close.start(cycle.id, cycle.version)
        budget = Budget(
            organization_id=actors.organization.id,
            name="Multi-period budget",
            start_date=date(2028, 3, 1),
            end_date=date(2028, 5, 31),
        )
        session.add(budget)
        session.commit()
        session.refresh(budget)
        session.add_all(
            [
                BudgetLine(budget_id=budget.id, account_id=expense.id, period_start=date(2028, 3, 1), amount=100),
                BudgetLine(budget_id=budget.id, account_id=expense.id, period_start=date(2028, 4, 1), amount=200),
                BudgetLine(budget_id=budget.id, account_id=expense.id, period_start=date(2028, 5, 1), amount=300),
            ]
        )
        session.commit()
        service = ReconciliationService(session, actors.organization.id, actors.preparer.id)
        rows = service.materialize_variances(
            cycle.id,
            budget_id=budget.id,
            horizon=90,
            absolute_threshold=Decimal("0"),
            percentage_threshold=None,
        )
        assert {row.period_start for row in rows} == {date(2028, 4, 1)}

        empty_budget = Budget(
            organization_id=actors.organization.id,
            name="Outside-only budget",
            start_date=date(2028, 3, 1),
            end_date=date(2028, 3, 31),
        )
        session.add(empty_budget)
        session.commit()
        session.refresh(empty_budget)
        session.add(
            BudgetLine(
                budget_id=empty_budget.id,
                account_id=expense.id,
                period_start=date(2028, 3, 1),
                amount=100,
            )
        )
        session.commit()
        service.materialize_variances(
            cycle.id,
            budget_id=empty_budget.id,
            horizon=30,
            absolute_threshold=Decimal("1000"),
            percentage_threshold=Decimal("0.10"),
        )
        latest = session.exec(select(VarianceReviewRun).order_by(VarianceReviewRun.id.desc())).first()
        assert latest is not None and latest.row_count == 0
        assert not any(blocker.code == "VARIANCE_REVIEW_NOT_RUN" for blocker in close.readiness(cycle.id).blockers)


def test_final_close_bundle_is_current_closed_and_exports_decision_history() -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id and actors.administrator.id
        preparer = CloseService(session, actors.organization.id, actors.preparer.id)
        period = preparer.create_period("Final evidence", date(2028, 5, 1), date(2028, 5, 31))
        cycle = preparer.create_cycle(period.id, "Final close", policy={"variance_review_required": False})
        cycle = preparer.start(cycle.id, cycle.version)
        attestation = next(
            task for task in preparer.list_checklist(cycle.id) if task.control_type == CloseTaskControlType.ATTESTATION
        )
        preparer.update_manual_task(
            cycle.id,
            attestation.id,
            version=attestation.version,
            complete=True,
            notes="Reviewed",
        )
        cycle = preparer.require_cycle(cycle.id)
        cycle = preparer.mark_ready(cycle.id, cycle.version)
        evidence = CloseEvidenceService(session, actors.organization.id, actors.preparer.id)
        evidence.record_generation(cycle.id, evidence.build_bundle(cycle.id))
        administrator = CloseService(session, actors.organization.id, actors.administrator.id)
        closed = administrator.close(cycle.id, cycle.version)
        assert closed.status == CloseCycleStatus.CLOSED
        assert closed.approved_at == closed.closed_at
        assert administrator.readiness(cycle.id).evidence_freshness == "CURRENT"
        bundle = CloseEvidenceService(session, actors.organization.id, actors.administrator.id).build_bundle(cycle.id)
        with ZipFile(BytesIO(bundle.content)) as archive:
            assert "journal-approval-decisions.csv" in archive.namelist()
            close_payload = json.loads(archive.read("close-cycle.json"))
            assert close_payload["cycle"]["status"] == "CLOSED"
            assert close_payload["period"]["status"] == "CLOSED"
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["source_revision"] == closed.content_revision
            assert manifest["evidence_kind"] == "FINAL"


def test_cycle_transition_compare_and_swap_allows_only_one_session(tmp_path) -> None:
    database = tmp_path / "close-cas.db"
    engine = create_engine(f"sqlite:///{database}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as seed:
        organization = Organization(name="CAS tenant")
        user = User(email="cas@example.test", password_hash="stub")
        seed.add_all([organization, user])
        seed.commit()
        seed.refresh(organization)
        seed.refresh(user)
        seed.add(Membership(user_id=user.id, organization_id=organization.id, can_manage_ledger=True))
        seed.commit()
        service = CloseService(seed, organization.id, user.id)
        period = service.create_period("CAS period", date(2028, 6, 1), date(2028, 6, 30))
        cycle = service.create_cycle(period.id, "CAS close", policy={"variance_review_required": False})
        organization_id = organization.id
        user_id = user.id
        cycle_id = cycle.id

    with Session(engine, expire_on_commit=False) as first, Session(engine, expire_on_commit=False) as second:
        first_cycle = first.get(CloseCycle, cycle_id)
        second_cycle = second.get(CloseCycle, cycle_id)
        assert first_cycle is not None and second_cycle is not None
        CloseService(first, organization_id, user_id).start(cycle_id, first_cycle.version)
        with pytest.raises(CloseConflictError, match="stale"):
            CloseService(second, organization_id, user_id).start(cycle_id, second_cycle.version)

    with Session(engine) as verify:
        persisted = verify.get(CloseCycle, cycle_id)
        assert persisted is not None
        assert persisted.status == CloseCycleStatus.IN_PROGRESS
        assert persisted.version == 2
        assert len(verify.exec(select(AuditLog).where(AuditLog.entity_name == "CloseCycle")).all()) == 2
    engine.dispose()


def test_final_evidence_build_failure_rolls_back_cycle_period_revision_and_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id and actors.administrator.id
        preparer = CloseService(session, actors.organization.id, actors.preparer.id)
        period = preparer.create_period("Rollback close", date(2028, 7, 1), date(2028, 7, 31))
        cycle = preparer.create_cycle(period.id, "Rollback close", policy={"variance_review_required": False})
        cycle = preparer.start(cycle.id, cycle.version)
        attestation = next(
            task for task in preparer.list_checklist(cycle.id) if task.control_type == CloseTaskControlType.ATTESTATION
        )
        preparer.update_manual_task(
            cycle.id,
            attestation.id,
            version=attestation.version,
            complete=True,
            notes="Reviewed",
        )
        cycle = preparer.require_cycle(cycle.id)
        cycle = preparer.mark_ready(cycle.id, cycle.version)
        evidence = CloseEvidenceService(session, actors.organization.id, actors.preparer.id)
        evidence.record_generation(cycle.id, evidence.build_bundle(cycle.id))
        before_cycle = preparer.require_cycle(cycle.id)
        before = (before_cycle.version, before_cycle.content_revision, len(session.exec(select(AuditLog)).all()))

        def fail_bundle(*_args, **_kwargs):
            raise RuntimeError("injected evidence build failure")

        monkeypatch.setattr(CloseEvidenceService, "build_bundle", fail_bundle)
        administrator = CloseService(session, actors.organization.id, actors.administrator.id)
        with pytest.raises(RuntimeError, match="injected"):
            administrator.close(cycle.id, cycle.version)

        persisted_cycle = administrator.require_cycle(cycle.id)
        persisted_period = administrator.require_period(period.id)
        assert persisted_cycle.status == CloseCycleStatus.READY_FOR_APPROVAL
        assert persisted_period.status == AccountingPeriodStatus.OPEN
        assert (persisted_cycle.version, persisted_cycle.content_revision) == before[:2]
        assert len(session.exec(select(AuditLog)).all()) == before[2]


def test_close_configuration_and_manual_control_guards() -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id and actors.administrator.id
        close = CloseService(session, actors.organization.id, actors.preparer.id)
        admin = CloseService(session, actors.organization.id, actors.administrator.id)
        ledger = LedgerService(session, actors.organization.id)
        cash = ledger.create_account("Guarded cash", "ASSET", code="1100")

        assert close.validate_owner(None) is None
        with pytest.raises(CloseNotFoundError, match="assignment"):
            close.validate_owner(999_999)
        with pytest.raises(CloseValidationError, match="label"):
            close.create_period(" ", date(2028, 8, 1), date(2028, 8, 31))
        with pytest.raises(CloseValidationError, match="start date"):
            close.create_period("Reverse", date(2028, 8, 31), date(2028, 8, 1))

        period = close.create_period("Guard period", date(2028, 8, 1), date(2028, 8, 31))
        with pytest.raises(CloseValidationError, match="name"):
            close.create_cycle(period.id, " ")
        with pytest.raises(CloseValidationError, match="journal_approval_mode"):
            close.create_cycle(period.id, "Bad mode", policy={"journal_approval_mode": "SOMETIMES"})
        with pytest.raises(CloseValidationError, match="positive account IDs"):
            close.create_cycle(period.id, "Bad scope", policy={"required_reconciliation_account_ids": [True]})
        with pytest.raises(CloseNotFoundError, match="reconciliation account"):
            close.create_cycle(period.id, "Foreign scope", policy={"required_reconciliation_account_ids": [999_999]})
        with pytest.raises(CloseValidationError, match="boolean"):
            close.create_cycle(period.id, "Bad variance", policy={"variance_review_required": "yes"})

        cycle = close.create_cycle(
            period.id,
            "Guarded close",
            policy={"required_reconciliation_account_ids": [cash.id], "variance_review_required": False},
        )
        with pytest.raises(CloseConflictError, match="already exists"):
            close.create_cycle(period.id, "Duplicate")
        cycle = close.start(cycle.id, cycle.version)
        with pytest.raises(CloseConflictError, match="Cannot transition"):
            close.start(cycle.id, cycle.version)
        with pytest.raises(CloseConflictError, match="ready for approval"):
            admin.close(cycle.id, cycle.version)
        with pytest.raises(CloseValidationError, match="title"):
            close.create_custom_task(cycle.id, title=" ")

        tasks = close.list_checklist(cycle.id)
        system_task = next(task for task in tasks if task.control_type == CloseTaskControlType.SYSTEM)
        final_task = next(task for task in tasks if task.task_key == "final_close_approved")
        with pytest.raises(CloseNotFoundError, match="Checklist"):
            close.update_manual_task(cycle.id, 999_999, version=1, complete=True)
        with pytest.raises(CloseConflictError, match="System-derived"):
            close.update_manual_task(cycle.id, system_task.id, version=system_task.version, complete=True)
        with pytest.raises(CloseConflictError, match="Final close"):
            close.update_manual_task(cycle.id, final_task.id, version=final_task.version, complete=True)
        with pytest.raises(CloseValidationError, match="return-to-work"):
            admin.return_to_work(cycle.id, cycle.version, " ")
        with pytest.raises(CloseValidationError, match="cancellation"):
            admin.cancel(cycle.id, cycle.version, " ")
        with pytest.raises(CloseValidationError, match="reopen"):
            admin.reopen(cycle.id, cycle.version, " ")


def test_reconciliation_variance_and_approval_decision_guards() -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id and actors.reviewer.id and actors.administrator.id
        close = CloseService(session, actors.organization.id, actors.preparer.id)
        ledger = LedgerService(session, actors.organization.id)
        cash = ledger.create_account("Decision cash", "ASSET", code="1200")
        revenue = ledger.create_account("Decision revenue", "REVENUE", code="4200")
        period = close.create_period("Decision period", date(2028, 9, 1), date(2028, 9, 30))
        cycle = close.create_cycle(period.id, "Decision close", policy={"variance_review_required": False})
        cycle = close.start(cycle.id, cycle.version)
        preparer = ReconciliationService(session, actors.organization.id, actors.preparer.id)
        reviewer = ReconciliationService(session, actors.organization.id, actors.reviewer.id)
        administrator = ReconciliationService(session, actors.organization.id, actors.administrator.id)

        row = preparer.prepare_reconciliation(
            cycle.id,
            cash.id,
            control_balance=Decimal("0"),
            tolerance=Decimal("0"),
        )
        with pytest.raises(CloseConflictError, match="already exists"):
            preparer.prepare_reconciliation(
                cycle.id,
                cash.id,
                control_balance=Decimal("0"),
                tolerance=Decimal("0"),
            )
        with pytest.raises(CloseValidationError, match="nonnegative"):
            preparer.update_reconciliation(
                cycle.id,
                row.id,
                account_id=cash.id,
                control_balance=Decimal("0"),
                tolerance=Decimal("-1"),
                version=row.version,
            )
        with pytest.raises(CloseConflictError, match="preparer"):
            preparer.approve_reconciliation(cycle.id, row.id, version=row.version)
        with pytest.raises(CloseConflictError, match="stale"):
            reviewer.approve_reconciliation(cycle.id, row.id, version=row.version + 1)
        approved_reconciliation = reviewer.approve_reconciliation(cycle.id, row.id, version=row.version)
        assert approved_reconciliation.status.value == "APPROVED"

        review = VarianceReview(
            organization_id=actors.organization.id,
            cycle_id=cycle.id,
            budget_id=1,
            account_id=cash.id,
            period_start=date(2028, 9, 1),
            horizon=30,
            budget_amount=Decimal("100"),
            actual_amount=Decimal("150"),
            variance_amount=Decimal("50"),
            absolute_threshold=Decimal("10"),
            is_material=True,
        )
        session.add(review)
        session.commit()
        session.refresh(review)
        with pytest.raises(CloseValidationError, match="reviewer note"):
            preparer.update_variance(
                cycle.id,
                review.id,
                version=review.version,
                disposition=VarianceDisposition.EXPLAINED,
                note=" ",
            )
        with pytest.raises(CloseConflictError, match="stale"):
            preparer.update_variance(
                cycle.id,
                review.id,
                version=review.version + 1,
                disposition=VarianceDisposition.UNRESOLVED,
                note=None,
            )

        transaction = ledger.post_transaction(
            date(2028, 9, 10),
            "Decision journal",
            [
                {"account_id": cash.id, "debit": 10, "credit": 0},
                {"account_id": revenue.id, "debit": 0, "credit": 10},
            ],
        )
        with pytest.raises(CloseValidationError, match="Exactly one"):
            preparer.request_approval(cycle.id)
        with pytest.raises(CloseValidationError, match="Exactly one"):
            preparer.request_approval(cycle.id, transaction_id=transaction.id, staged_transaction_id=1)
        approval = preparer.request_approval(cycle.id, transaction_id=transaction.id)
        assert preparer.request_approval(cycle.id, transaction_id=transaction.id).id == approval.id
        assert (
            reviewer.decide_approval(
                cycle.id,
                approval.id,
                version=approval.version,
                decision=JournalApprovalStatus.REQUESTED,
                reason=None,
            ).id
            == approval.id
        )
        with pytest.raises(CloseConflictError, match="own request"):
            preparer.decide_approval(
                cycle.id,
                approval.id,
                version=approval.version,
                decision=JournalApprovalStatus.APPROVED,
                reason=None,
            )
        with pytest.raises(CloseConflictError, match="Cannot change"):
            reviewer.decide_approval(
                cycle.id,
                approval.id,
                version=approval.version,
                decision=JournalApprovalStatus.REVOKED,
                reason="Not yet approved",
            )
        with pytest.raises(CloseValidationError, match="reason"):
            reviewer.decide_approval(
                cycle.id,
                approval.id,
                version=approval.version,
                decision=JournalApprovalStatus.REJECTED,
                reason=" ",
            )
        approval = reviewer.decide_approval(
            cycle.id,
            approval.id,
            version=approval.version,
            decision=JournalApprovalStatus.APPROVED,
            reason="Reviewed",
        )
        with pytest.raises(CloseConflictError, match="Administrator"):
            reviewer.decide_approval(
                cycle.id,
                approval.id,
                version=approval.version,
                decision=JournalApprovalStatus.REVOKED,
                reason="Reopen review",
            )
        with pytest.raises(CloseValidationError, match="reason"):
            administrator.decide_approval(
                cycle.id,
                approval.id,
                version=approval.version,
                decision=JournalApprovalStatus.REVOKED,
                reason=" ",
                is_admin=True,
            )
