from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from io import BytesIO
from threading import Barrier, Event, Thread, current_thread
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
    JournalEntry,
    Membership,
    Organization,
    StagedPosting,
    StagedTransaction,
    Transaction,
    User,
    VarianceDisposition,
    VarianceReview,
    VarianceReviewRun,
    WorkflowStatus,
)
from apps.api.services import period_lock
from apps.api.services.close_evidence_service import CloseEvidenceService
from apps.api.services.close_service import (
    CloseConflictError,
    CloseNotFoundError,
    CloseService,
    CloseValidationError,
)
from apps.api.services.ledger_service import LedgerService
from apps.api.services.period_lock import PeriodPostingError
from apps.api.services.reconciliation_service import ReconciliationService
from apps.api.services.workflow_service import WorkflowService
from sqlmodel import Session, SQLModel, create_engine, select

from tests._close_helpers import close_session


def _create_cycle_without_variance(session, actors, period_id: int, name: str):
    assert actors.organization.id and actors.preparer.id and actors.administrator.id
    return CloseService(session, actors.organization.id, actors.administrator.id).create_cycle(
        period_id,
        name,
        owner_user_id=actors.preparer.id,
        policy={"variance_review_required": False, "override_reason": "Focused regression fixture"},
    )


def test_cancelled_cycle_is_immutable_and_restart_preserves_period_and_evidence() -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id and actors.administrator.id
        preparer = CloseService(session, actors.organization.id, actors.preparer.id)
        administrator = CloseService(session, actors.organization.id, actors.administrator.id)
        period = preparer.create_period("Restartable period", date(2028, 1, 1), date(2028, 1, 31))
        cycle = _create_cycle_without_variance(session, actors, period.id, "Restartable close")
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
        cycle = _create_cycle_without_variance(session, actors, period.id, "Path scoped close")
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
        cycle = _create_cycle_without_variance(session, actors, period.id, "Approval close")
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
        cycle = _create_cycle_without_variance(session, actors, period.id, "Final close")
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
        seed.add(Membership(user_id=user.id, organization_id=organization.id, can_manage_ledger=True, is_admin=True))
        seed.commit()
        service = CloseService(seed, organization.id, user.id)
        period = service.create_period("CAS period", date(2028, 6, 1), date(2028, 6, 30))
        cycle = service.create_cycle(
            period.id,
            "CAS close",
            policy={"variance_review_required": False, "override_reason": "Focused CAS fixture"},
        )
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


def test_overlapping_period_creation_is_serialized_across_sessions(tmp_path) -> None:
    database = tmp_path / "period-create-race.db"
    engine = create_engine(
        f"sqlite:///{database}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as seed:
        organization = Organization(name="Period race tenant")
        user = User(email="period-race@example.test", password_hash="stub")
        seed.add_all([organization, user])
        seed.commit()
        seed.refresh(organization)
        seed.refresh(user)
        seed.add(Membership(user_id=user.id, organization_id=organization.id, can_manage_ledger=True))
        seed.commit()
        organization_id = organization.id
        user_id = user.id

    start = Barrier(2)

    def create(label: str, start_date: date, end_date: date) -> str:
        with Session(engine, expire_on_commit=False) as session:
            start.wait()
            try:
                CloseService(session, organization_id, user_id).create_period(label, start_date, end_date)
            except CloseConflictError:
                return "conflict"
            return "created"

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(create, "Race A", date(2028, 10, 1), date(2028, 10, 31))
        second = pool.submit(create, "Race B", date(2028, 10, 15), date(2028, 11, 15))
        assert sorted([first.result(), second.result()]) == ["conflict", "created"]
    with Session(engine) as verify:
        periods = verify.exec(select(AccountingPeriod)).all()
        assert len(periods) == 1
        assert periods[0].status == AccountingPeriodStatus.OPEN
    engine.dispose()


@pytest.mark.parametrize("posting_path", ["direct", "workflow"])
@pytest.mark.parametrize("winner", ["close", "posting"])
def test_final_close_serializes_against_direct_and_workflow_posting(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    posting_path: str,
    winner: str,
) -> None:
    database = tmp_path / f"close-{posting_path}-{winner}-race.db"
    engine = create_engine(
        f"sqlite:///{database}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as seed:
        organization = Organization(name=f"Close {posting_path} race tenant")
        administrator = User(email=f"close-{posting_path}-race@example.test", password_hash="stub")
        seed.add_all([organization, administrator])
        seed.commit()
        seed.refresh(organization)
        seed.refresh(administrator)
        seed.add(
            Membership(
                user_id=administrator.id,
                organization_id=organization.id,
                can_manage_ledger=True,
                is_admin=True,
            )
        )
        seed.commit()
        ledger = LedgerService(seed, organization.id)
        cash = ledger.create_account("Race cash", "ASSET", code="1000")
        revenue = ledger.create_account("Race revenue", "REVENUE", code="4000")
        close = CloseService(seed, organization.id, administrator.id)
        period = close.create_period("Close race", date(2028, 11, 1), date(2028, 11, 30))
        cycle = close.create_cycle(
            period.id,
            "Close race",
            policy={
                "required_reconciliation_account_ids": [],
                "reconciliation_scope_not_applicable": True,
                "variance_review_required": False,
                "override_reason": "Concurrent posting regression fixture",
            },
        )
        cycle = close.start(cycle.id, cycle.version)
        if winner == "close":
            attestation = next(
                task for task in close.list_checklist(cycle.id) if task.control_type == CloseTaskControlType.ATTESTATION
            )
            close.update_manual_task(
                cycle.id,
                attestation.id,
                version=attestation.version,
                complete=True,
                notes="Reviewed",
            )
            cycle = close.require_cycle(cycle.id)
            cycle = close.mark_ready(cycle.id, cycle.version)
        else:
            ReconciliationService(seed, organization.id, administrator.id).prepare_reconciliation(
                cycle.id,
                cash.id,
                control_balance=Decimal("0"),
                tolerance=Decimal("0"),
            )
            budget = Budget(
                organization_id=organization.id,
                name="Posting-wins variance state",
                start_date=date(2028, 11, 1),
                end_date=date(2028, 11, 30),
            )
            seed.add(budget)
            seed.flush()
            seed.add(
                BudgetLine(
                    budget_id=budget.id,
                    account_id=revenue.id,
                    period_start=date(2028, 11, 1),
                    amount=Decimal("-10"),
                )
            )
            seed.commit()
            ReconciliationService(seed, organization.id, administrator.id).materialize_variances(
                cycle.id,
                budget_id=budget.id,
                horizon=30,
                absolute_threshold=Decimal("0"),
                percentage_threshold=None,
            )
            cycle = close.require_cycle(cycle.id)
        evidence = CloseEvidenceService(seed, organization.id, administrator.id)
        evidence.record_generation(cycle.id, evidence.build_bundle(cycle.id))
        staged_id = None
        if posting_path == "workflow":
            staged = StagedTransaction(
                date=date(2028, 11, 20),
                description="Concurrent workflow posting",
                source="race-test",
                status=WorkflowStatus.POSTED,
            )
            seed.add(staged)
            seed.flush()
            seed.add_all(
                [
                    StagedPosting(staged_transaction_id=staged.id, account_id=cash.id, debit=10, credit=0),
                    StagedPosting(staged_transaction_id=staged.id, account_id=revenue.id, debit=0, credit=10),
                ]
            )
            seed.commit()
            staged_id = staged.id
        organization_id = organization.id
        administrator_id = administrator.id
        cycle_id = cycle.id
        cycle_version = cycle.version
        cash_id = cash.id
        revenue_id = revenue.id
        period_id = period.id

    original_gate = period_lock.acquire_period_write_gate
    winner_has_gate = Event()
    contender_attempted_gate = Event()

    def coordinated_gate(session: Session, target_organization_id: int) -> None:
        writer = current_thread().name
        is_winner = writer == f"{winner}-writer"
        if is_winner and not winner_has_gate.is_set():
            original_gate(session, target_organization_id)
            winner_has_gate.set()
            if not contender_attempted_gate.wait(timeout=10):
                raise AssertionError("Contending writer did not reach the period write gate")
            return
        if not is_winner:
            contender_attempted_gate.set()
        original_gate(session, target_organization_id)

    monkeypatch.setattr(period_lock, "acquire_period_write_gate", coordinated_gate)
    outcomes: dict[str, str] = {}

    def run_close() -> None:
        with Session(engine, expire_on_commit=False) as session:
            try:
                closed = CloseService(session, organization_id, administrator_id).close(cycle_id, cycle_version)
            except CloseConflictError as exc:
                outcomes["close"] = str(exc)
            else:
                outcomes["close"] = closed.status.value

    def run_post() -> None:
        with Session(engine, expire_on_commit=False) as session:
            try:
                if posting_path == "direct":
                    LedgerService(session, organization_id).post_transaction(
                        date(2028, 11, 20),
                        "Concurrent direct posting",
                        [
                            {"account_id": cash_id, "debit": 10, "credit": 0},
                            {"account_id": revenue_id, "debit": 0, "credit": 10},
                        ],
                    )
                else:
                    assert staged_id is not None
                    WorkflowService(session).process_transactions([staged_id])
            except PeriodPostingError as exc:
                outcomes["posting"] = exc.code
            else:
                outcomes["posting"] = "posted"

    close_thread = Thread(target=run_close, name="close-writer")
    posting_thread = Thread(target=run_post, name="posting-writer")
    winning_thread = close_thread if winner == "close" else posting_thread
    losing_thread = posting_thread if winner == "close" else close_thread
    winning_thread.start()
    assert winner_has_gate.wait(timeout=10), "Winning writer did not acquire the period write gate"
    losing_thread.start()
    winning_thread.join(timeout=20)
    losing_thread.join(timeout=20)
    assert not winning_thread.is_alive() and not losing_thread.is_alive()

    with Session(engine) as verify:
        persisted_period = verify.get(AccountingPeriod, period_id)
        persisted_cycle = verify.get(CloseCycle, cycle_id)
        assert persisted_period is not None and persisted_cycle is not None
        transactions = verify.exec(select(Transaction).order_by(Transaction.id)).all()
        journals = verify.exec(select(JournalEntry).order_by(JournalEntry.id)).all()
        if winner == "close":
            assert outcomes["close"] == CloseCycleStatus.CLOSED.value
            assert outcomes["posting"] in {"ACCOUNTING_PERIOD_CLOSE_READY", "ACCOUNTING_PERIOD_CLOSED"}
            assert persisted_cycle.status == CloseCycleStatus.CLOSED
            assert persisted_period.status == AccountingPeriodStatus.CLOSED
            assert persisted_period.ledger_activity_revision == 1
            assert transactions == [] and journals == []
        else:
            assert outcomes["posting"] == "posted"
            assert outcomes["close"] == "Close cycle must be ready for approval before final close"
            assert persisted_cycle.status == CloseCycleStatus.IN_PROGRESS
            assert persisted_period.status == AccountingPeriodStatus.OPEN
            assert persisted_period.ledger_activity_revision == 2
            assert len(transactions) == 1 and len(journals) == 2
            assert sum(Decimal(str(row.debit)) for row in journals) == sum(Decimal(str(row.credit)) for row in journals)
            latest_evidence = verify.exec(
                select(CloseEvidence).where(CloseEvidence.cycle_id == cycle_id).order_by(CloseEvidence.id.desc())
            ).first()
            reconciliation = verify.exec(
                select(AccountReconciliation).where(AccountReconciliation.cycle_id == cycle_id)
            ).one()
            variance_run = verify.exec(select(VarianceReviewRun).where(VarianceReviewRun.cycle_id == cycle_id)).one()
            assert latest_evidence is not None
            assert latest_evidence.source_ledger_activity_revision == 1
            assert reconciliation.ledger_activity_revision == 1
            assert variance_run.ledger_activity_revision == 1
            readiness = CloseService(verify, organization_id, administrator_id).readiness(cycle_id)
            assert readiness.ledger_activity_revision == 2
            assert readiness.evidence_freshness == "STALE"
    engine.dispose()


def test_evidence_persistence_rejects_a_source_changed_by_another_session(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "evidence-source-race.db"
    engine = create_engine(f"sqlite:///{database}", connect_args={"check_same_thread": False, "timeout": 30})
    SQLModel.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as seed:
        organization = Organization(name="Evidence source race tenant")
        user = User(email="evidence-source-race@example.test", password_hash="stub")
        seed.add_all([organization, user])
        seed.commit()
        seed.refresh(organization)
        seed.refresh(user)
        seed.add(Membership(user_id=user.id, organization_id=organization.id, can_manage_ledger=True))
        seed.commit()
        close = CloseService(seed, organization.id, user.id)
        period = close.create_period("Evidence race", date(2028, 12, 1), date(2028, 12, 31))
        cycle = close.create_cycle(period.id, "Evidence race")
        organization_id = organization.id
        user_id = user.id
        cycle_id = cycle.id

    with Session(engine, expire_on_commit=False) as snapshot_session:
        evidence = CloseEvidenceService(snapshot_session, organization_id, user_id)
        bundle = evidence.build_bundle(cycle_id)
        original_require_period = evidence.close.require_period
        source_mutated = False

        def require_period_and_mutate(period_id: int):
            nonlocal source_mutated
            period = original_require_period(period_id)
            if not source_mutated:
                source_mutated = True
                with Session(engine, expire_on_commit=False) as writer:
                    CloseService(writer, organization_id, user_id).create_custom_task(
                        cycle_id,
                        title="Concurrent source mutation",
                    )
            return period

        monkeypatch.setattr(evidence.close, "require_period", require_period_and_mutate)
        with pytest.raises(CloseConflictError, match="source changed"):
            evidence.record_generation(cycle_id, bundle)
    with Session(engine) as verify:
        assert verify.exec(select(CloseEvidence)).all() == []
    engine.dispose()


def test_final_evidence_build_failure_rolls_back_cycle_period_revision_and_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id and actors.administrator.id
        preparer = CloseService(session, actors.organization.id, actors.preparer.id)
        period = preparer.create_period("Rollback close", date(2028, 7, 1), date(2028, 7, 31))
        cycle = _create_cycle_without_variance(session, actors, period.id, "Rollback close")
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
        with pytest.raises(CloseConflictError, match="administrator"):
            close.create_cycle(
                period.id,
                "Manager override",
                policy={"variance_review_required": False, "override_reason": "Unauthorized"},
            )
        with pytest.raises(CloseValidationError, match="journal_approval_mode"):
            admin.create_cycle(
                period.id,
                "Bad mode",
                policy={"journal_approval_mode": "SOMETIMES", "override_reason": "Invalid fixture"},
            )
        with pytest.raises(CloseValidationError, match="positive account IDs"):
            admin.create_cycle(
                period.id,
                "Bad scope",
                policy={"required_reconciliation_account_ids": [True], "override_reason": "Invalid fixture"},
            )
        with pytest.raises(CloseNotFoundError, match="reconciliation account"):
            admin.create_cycle(
                period.id,
                "Foreign scope",
                policy={"required_reconciliation_account_ids": [999_999], "override_reason": "Invalid fixture"},
            )
        with pytest.raises(CloseValidationError, match="boolean"):
            admin.create_cycle(
                period.id,
                "Bad variance",
                policy={"variance_review_required": "yes", "override_reason": "Invalid fixture"},
            )

        cycle = admin.create_cycle(
            period.id,
            "Guarded close",
            owner_user_id=actors.preparer.id,
            policy={
                "required_reconciliation_account_ids": [cash.id],
                "variance_review_required": False,
                "override_reason": "Focused guard fixture",
            },
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
        cycle = _create_cycle_without_variance(session, actors, period.id, "Decision close")
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
