"""Reconciliation, variance-review, and journal-approval controls."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ..limits import MAX_RECONCILIATIONS_PER_CYCLE, MAX_VARIANCE_REVIEW_ROWS
from ..metadata_limits import validate_metadata
from ..models.models import (
    Account,
    AccountReconciliation,
    AuditAction,
    Budget,
    CloseCycle,
    JournalApproval,
    JournalApprovalDecision,
    JournalApprovalStatus,
    JournalEntry,
    ReconciliationStatus,
    StagedPosting,
    StagedTransaction,
    Transaction,
    VarianceDisposition,
    VarianceReview,
    VarianceReviewRun,
)
from .budget_service import BudgetService
from .close_service import (
    OPERATIONAL_CYCLE_STATES,
    CloseConflictError,
    CloseNotFoundError,
    CloseService,
    CloseValidationError,
)


class ReconciliationService:
    """Server-derived accounting controls for one tenant."""

    def __init__(self, session: Session, organization_id: int, actor_user_id: int):
        self.s = session
        self.organization_id = organization_id
        self.actor_user_id = actor_user_id
        self.close = CloseService(session, organization_id, actor_user_id)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    def _cycle_and_period(self, cycle_id: int, *, mutation: str | None = None) -> tuple[CloseCycle, Any]:
        cycle = (
            self.close.require_cycle_mutation(cycle_id, allowed=OPERATIONAL_CYCLE_STATES, operation=mutation)
            if mutation
            else self.close.require_cycle(cycle_id)
        )
        return cycle, self.close.require_period(cycle.period_id)

    def _account(self, account_id: int) -> Account:
        account = self.s.exec(
            select(Account).where(Account.organization_id == self.organization_id, Account.id == account_id)
        ).first()
        if account is None:
            raise CloseNotFoundError("Account not found")
        return account

    def ledger_ending_balance(self, cycle_id: int, account_id: int) -> Decimal:
        _, period = self._cycle_and_period(cycle_id)
        self._account(account_id)
        stmt = (
            select(JournalEntry, Transaction)
            .join(Transaction, cast(Any, Transaction.id) == cast(Any, JournalEntry.transaction_id))
            .where(
                JournalEntry.account_id == account_id,
                Transaction.organization_id == self.organization_id,
                cast(Any, Transaction.date) <= period.end_date,
            )
        )
        balance = Decimal("0")
        for entry, _ in self.s.exec(stmt):
            balance += Decimal(str(entry.debit or 0)) - Decimal(str(entry.credit or 0))
        return balance

    @staticmethod
    def _derive_reconciliation_status(
        control_balance: Decimal | None,
        difference: Decimal | None,
        tolerance: Decimal,
        notes: str | None,
    ) -> ReconciliationStatus:
        if control_balance is None or difference is None:
            return ReconciliationStatus.UNSTARTED
        if abs(difference) <= tolerance:
            return ReconciliationStatus.MATCHED
        if notes and notes.strip():
            return ReconciliationStatus.IN_PROGRESS
        return ReconciliationStatus.EXCEPTION

    def prepare_reconciliation(
        self,
        cycle_id: int,
        account_id: int,
        *,
        control_balance: Decimal | None,
        tolerance: Decimal,
        notes: str | None = None,
        evidence_metadata: dict[str, Any] | None = None,
        owner_user_id: int | None = None,
        version: int | None = None,
    ) -> AccountReconciliation:
        cycle, period = self._cycle_and_period(cycle_id, mutation="Reconciliation preparation")
        self._account(account_id)
        owner = owner_user_id or self.actor_user_id
        self.close.validate_owner(owner)
        tolerance = Decimal(str(tolerance))
        if tolerance < 0:
            raise CloseValidationError("Reconciliation tolerance must be nonnegative")
        ledger_balance = self.ledger_ending_balance(cycle_id, account_id)
        normalized_control = Decimal(str(control_balance)) if control_balance is not None else None
        difference = normalized_control - ledger_balance if normalized_control is not None else None
        normalized_notes = notes.strip() if notes else None
        status = self._derive_reconciliation_status(normalized_control, difference, tolerance, normalized_notes)
        metadata = cast(dict[str, Any], validate_metadata(evidence_metadata or {}))
        existing = self.s.exec(
            select(AccountReconciliation).where(
                AccountReconciliation.organization_id == self.organization_id,
                AccountReconciliation.cycle_id == cycle_id,
                AccountReconciliation.account_id == account_id,
            )
        ).first()
        now = self._now()
        if existing is None:
            reconciliation_ids = list(
                self.s.exec(
                    select(AccountReconciliation.id)
                    .where(
                        AccountReconciliation.organization_id == self.organization_id,
                        AccountReconciliation.cycle_id == cycle_id,
                    )
                    .limit(MAX_RECONCILIATIONS_PER_CYCLE)
                )
            )
            if len(reconciliation_ids) >= MAX_RECONCILIATIONS_PER_CYCLE:
                raise CloseValidationError("Maximum reconciliations per close cycle reached")
            reconciliation = AccountReconciliation(
                organization_id=self.organization_id,
                cycle_id=cycle_id,
                account_id=account_id,
                ledger_ending_balance=ledger_balance,
                control_balance=normalized_control,
                difference=difference,
                tolerance=tolerance,
                status=status,
                owner_user_id=owner,
                prepared_by_id=self.actor_user_id,
                prepared_at=now,
                ledger_activity_revision=period.ledger_activity_revision,
                notes=normalized_notes,
                evidence_metadata=metadata,
                created_at=now,
                updated_at=now,
            )
            before = None
            event = "reconciliation_prepared"
        else:
            if version is None:
                raise CloseConflictError("A reconciliation already exists for this account")
            return self.update_reconciliation(
                cycle_id,
                self.close._id(existing.id, "reconciliation"),
                account_id=account_id,
                control_balance=control_balance,
                tolerance=tolerance,
                notes=notes,
                evidence_metadata=evidence_metadata,
                owner_user_id=owner_user_id,
                version=version,
            )
        self.s.add(reconciliation)
        self.s.flush()
        self.close.bump_content_revision(cycle)
        self.close._audit(
            AuditAction.CREATE if before is None else AuditAction.UPDATE,
            "AccountReconciliation",
            reconciliation.id,
            before=before,
            after={
                "status": reconciliation.status.value,
                "version": reconciliation.version,
                "account_id": account_id,
                "difference": str(difference) if difference is not None else None,
            },
            event=event,
        )
        self.s.commit()
        self.s.refresh(reconciliation)
        return reconciliation

    def update_reconciliation(
        self,
        cycle_id: int,
        reconciliation_id: int,
        *,
        account_id: int,
        control_balance: Decimal | None,
        tolerance: Decimal,
        version: int,
        notes: str | None = None,
        evidence_metadata: dict[str, Any] | None = None,
        owner_user_id: int | None = None,
    ) -> AccountReconciliation:
        cycle, period = self._cycle_and_period(cycle_id, mutation="Reconciliation update")
        reconciliation = self.s.exec(
            select(AccountReconciliation).where(
                AccountReconciliation.organization_id == self.organization_id,
                AccountReconciliation.cycle_id == cycle_id,
                AccountReconciliation.id == reconciliation_id,
            )
        ).first()
        if reconciliation is None or reconciliation.account_id != account_id:
            raise CloseNotFoundError("Reconciliation not found")
        self._account(account_id)
        owner = owner_user_id or reconciliation.owner_user_id
        self.close.validate_owner(owner)
        normalized_tolerance = Decimal(str(tolerance))
        if normalized_tolerance < 0:
            raise CloseValidationError("Reconciliation tolerance must be nonnegative")
        ledger_balance = self.ledger_ending_balance(cycle_id, account_id)
        normalized_control = Decimal(str(control_balance)) if control_balance is not None else None
        difference = normalized_control - ledger_balance if normalized_control is not None else None
        normalized_notes = notes.strip() if notes else None
        status = self._derive_reconciliation_status(
            normalized_control,
            difference,
            normalized_tolerance,
            normalized_notes,
        )
        metadata = cast(dict[str, Any], validate_metadata(evidence_metadata or {}))
        before = {"status": reconciliation.status.value, "version": reconciliation.version}
        now = self._now()
        self.close.bump_content_revision(cycle)
        result = self.s.exec(
            update(AccountReconciliation)
            .where(
                cast(Any, AccountReconciliation.id) == reconciliation_id,
                cast(Any, AccountReconciliation.organization_id) == self.organization_id,
                cast(Any, AccountReconciliation.cycle_id) == cycle_id,
                cast(Any, AccountReconciliation.account_id) == account_id,
                cast(Any, AccountReconciliation.version) == version,
            )
            .values(
                ledger_ending_balance=ledger_balance,
                control_balance=normalized_control,
                difference=difference,
                tolerance=normalized_tolerance,
                status=status,
                owner_user_id=owner,
                prepared_by_id=self.actor_user_id,
                prepared_at=now,
                reviewer_user_id=None,
                approved_by_id=None,
                reviewed_at=None,
                approved_at=None,
                notes=normalized_notes,
                evidence_metadata=metadata,
                ledger_activity_revision=period.ledger_activity_revision,
                version=version + 1,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if getattr(result, "rowcount", 0) != 1:
            self.s.rollback()
            raise CloseConflictError("Reconciliation version is stale")
        self.s.expire(reconciliation)
        self.s.refresh(reconciliation)
        self.close._audit(
            AuditAction.UPDATE,
            "AccountReconciliation",
            reconciliation.id,
            before=before,
            after={
                "status": reconciliation.status.value,
                "version": reconciliation.version,
                "account_id": account_id,
                "difference": str(difference) if difference is not None else None,
            },
            event="reconciliation_updated",
        )
        self.s.commit()
        self.s.refresh(reconciliation)
        return reconciliation

    def approve_reconciliation(self, cycle_id: int, reconciliation_id: int, *, version: int) -> AccountReconciliation:
        cycle, period = self._cycle_and_period(cycle_id, mutation="Reconciliation approval")
        reconciliation = self.s.exec(
            select(AccountReconciliation).where(
                AccountReconciliation.organization_id == self.organization_id,
                AccountReconciliation.cycle_id == cycle_id,
                AccountReconciliation.id == reconciliation_id,
            )
        ).first()
        if reconciliation is None:
            raise CloseNotFoundError("Reconciliation not found")
        if reconciliation.version != version:
            raise CloseConflictError("Reconciliation version is stale")
        if reconciliation.ledger_activity_revision != period.ledger_activity_revision:
            raise CloseConflictError("Reconciliation predates current ledger activity and must be re-prepared")
        if reconciliation.prepared_by_id == self.actor_user_id:
            raise CloseConflictError("The reconciliation preparer cannot provide final approval")
        if reconciliation.status not in {ReconciliationStatus.MATCHED, ReconciliationStatus.IN_PROGRESS}:
            raise CloseConflictError("Only matched or documented reconciliations can be approved")
        before = {"status": reconciliation.status.value, "version": reconciliation.version}
        now = self._now()
        self.close.bump_content_revision(cycle)
        result = self.s.exec(
            update(AccountReconciliation)
            .where(
                cast(Any, AccountReconciliation.id) == reconciliation_id,
                cast(Any, AccountReconciliation.organization_id) == self.organization_id,
                cast(Any, AccountReconciliation.cycle_id) == cycle_id,
                cast(Any, AccountReconciliation.version) == version,
            )
            .values(
                status=ReconciliationStatus.APPROVED,
                reviewer_user_id=self.actor_user_id,
                approved_by_id=self.actor_user_id,
                reviewed_at=now,
                approved_at=now,
                version=version + 1,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if getattr(result, "rowcount", 0) != 1:
            self.s.rollback()
            raise CloseConflictError("Reconciliation version is stale")
        self.s.expire(reconciliation)
        self.s.refresh(reconciliation)
        self.close._audit(
            AuditAction.UPDATE,
            "AccountReconciliation",
            reconciliation.id,
            before=before,
            after={"status": reconciliation.status.value, "version": reconciliation.version},
            event="reconciliation_approved",
        )
        self.s.commit()
        self.s.refresh(reconciliation)
        return reconciliation

    def list_reconciliations(self, cycle_id: int) -> list[AccountReconciliation]:
        self.close.require_cycle(cycle_id)
        return list(
            self.s.exec(
                select(AccountReconciliation)
                .where(
                    AccountReconciliation.organization_id == self.organization_id,
                    AccountReconciliation.cycle_id == cycle_id,
                )
                .order_by(cast(Any, AccountReconciliation.account_id))
            )
        )

    def materialize_variances(
        self,
        cycle_id: int,
        *,
        budget_id: int,
        horizon: int,
        absolute_threshold: Decimal,
        percentage_threshold: Decimal | None,
        refresh: bool = True,
    ) -> list[VarianceReview]:
        cycle, period = self._cycle_and_period(cycle_id, mutation="Variance review run")
        budget = self.s.exec(
            select(Budget).where(Budget.organization_id == self.organization_id, Budget.id == budget_id)
        ).first()
        if budget is None:
            raise CloseNotFoundError("Budget not found")
        absolute = Decimal(str(absolute_threshold))
        percentage = Decimal(str(percentage_threshold)) if percentage_threshold is not None else None
        if absolute < 0 or (percentage is not None and percentage < 0):
            raise CloseValidationError("Materiality thresholds must be nonnegative")
        report = BudgetService(self.s).budget_vs_actual(budget_id, horizon=horizon, refresh=refresh)
        period_lines = [line for line in report.lines if period.start_date <= line.period_start <= period.end_date]
        if len(period_lines) > MAX_VARIANCE_REVIEW_ROWS:
            raise CloseValidationError("Budget report exceeds the maximum variance review rows")
        new_revision = self.close.bump_content_revision(cycle)
        run = VarianceReviewRun(
            organization_id=self.organization_id,
            cycle_id=cycle_id,
            budget_id=budget_id,
            horizon=horizon,
            absolute_threshold=absolute,
            percentage_threshold=percentage,
            report_parameters={
                "refresh": refresh,
                "period_start": str(period.start_date),
                "period_end": str(period.end_date),
            },
            report_provenance={
                "plan_id": report.metadata.get("plan_id"),
                "plan_revision": str(report.metadata.get("plan_revision") or ""),
                "generated_at": str(report.metadata.get("generated_at") or ""),
                "reporting_currency": report.metadata.get("reporting_currency"),
            },
            generated_by_id=self.actor_user_id,
            row_count=len(period_lines),
            content_revision=new_revision,
            ledger_activity_revision=period.ledger_activity_revision,
        )
        self.s.add(run)
        self.s.flush()
        run_id = self.close._id(run.id, "variance review run")
        created: list[VarianceReview] = []
        for line in period_lines:
            budget_amount = Decimal(str(line.budget_amount))
            actual_amount = Decimal(str(line.actual_amount))
            variance = Decimal(str(line.variance))
            variance_percent = abs(variance / budget_amount) if budget_amount != 0 else None
            is_material = abs(variance) >= absolute or (
                percentage is not None and variance_percent is not None and variance_percent >= percentage
            )
            review = VarianceReview(
                organization_id=self.organization_id,
                cycle_id=cycle_id,
                run_id=run_id,
                budget_id=budget_id,
                account_id=line.account_id,
                period_start=line.period_start,
                horizon=horizon,
                budget_amount=budget_amount,
                actual_amount=actual_amount,
                variance_amount=variance,
                variance_percent=variance_percent,
                absolute_threshold=absolute,
                percentage_threshold=percentage,
                is_material=is_material,
                report_metadata={
                    "budget_id": budget_id,
                    "horizon": horizon,
                    "plan_id": report.metadata.get("plan_id"),
                    "plan_revision": str(report.metadata.get("plan_revision") or ""),
                    "generated_at": str(report.metadata.get("generated_at") or ""),
                    "reporting_currency": report.metadata.get("reporting_currency"),
                },
            )
            self.s.add(review)
            created.append(review)
        self.close._audit(
            AuditAction.CREATE,
            "VarianceReviewRun",
            run.id,
            after={
                "cycle_id": cycle_id,
                "budget_id": budget_id,
                "rows_created": len(created),
                "period_rows": len(period_lines),
                "content_revision": new_revision,
                "ledger_activity_revision": period.ledger_activity_revision,
            },
            event="variance_reviews_materialized",
        )
        self.s.commit()
        for review in created:
            self.s.refresh(review)
        return self.list_variances(cycle_id)

    def list_variances(self, cycle_id: int) -> list[VarianceReview]:
        self.close.require_cycle(cycle_id)
        latest_run = self.s.exec(
            select(VarianceReviewRun)
            .where(
                VarianceReviewRun.organization_id == self.organization_id,
                VarianceReviewRun.cycle_id == cycle_id,
            )
            .order_by(cast(Any, VarianceReviewRun.id).desc())
        ).first()
        if latest_run is None:
            return []
        return list(
            self.s.exec(
                select(VarianceReview)
                .where(
                    VarianceReview.organization_id == self.organization_id,
                    VarianceReview.cycle_id == cycle_id,
                    VarianceReview.run_id == latest_run.id,
                )
                .order_by(cast(Any, VarianceReview.period_start), cast(Any, VarianceReview.account_id))
            )
        )

    def update_variance(
        self,
        cycle_id: int,
        review_id: int,
        *,
        version: int,
        disposition: VarianceDisposition,
        note: str | None,
        owner_user_id: int | None = None,
    ) -> VarianceReview:
        cycle, _ = self._cycle_and_period(cycle_id, mutation="Variance disposition update")
        review = self.s.exec(
            select(VarianceReview).where(
                VarianceReview.organization_id == self.organization_id,
                VarianceReview.cycle_id == cycle_id,
                VarianceReview.id == review_id,
            )
        ).first()
        if review is None:
            raise CloseNotFoundError("Variance review not found")
        latest_run_id = self.s.exec(
            select(VarianceReviewRun.id)
            .where(
                VarianceReviewRun.organization_id == self.organization_id,
                VarianceReviewRun.cycle_id == cycle_id,
            )
            .order_by(cast(Any, VarianceReviewRun.id).desc())
        ).first()
        if review.run_id != latest_run_id:
            raise CloseConflictError("Only the latest variance review run can be updated")
        owner = owner_user_id or review.owner_user_id
        self.close.validate_owner(owner)
        if review.is_material and disposition != VarianceDisposition.UNRESOLVED and not (note or "").strip():
            raise CloseValidationError("A reviewer note is required for a material variance disposition")
        before = {"disposition": review.disposition.value, "version": review.version}
        now = self._now()
        self.close.bump_content_revision(cycle)
        result = self.s.exec(
            update(VarianceReview)
            .where(
                cast(Any, VarianceReview.id) == review_id,
                cast(Any, VarianceReview.organization_id) == self.organization_id,
                cast(Any, VarianceReview.cycle_id) == cycle_id,
                cast(Any, VarianceReview.version) == version,
            )
            .values(
                disposition=disposition,
                note=note.strip() if note else None,
                owner_user_id=owner,
                reviewer_user_id=self.actor_user_id,
                reviewed_at=now if disposition != VarianceDisposition.UNRESOLVED else None,
                version=version + 1,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if getattr(result, "rowcount", 0) != 1:
            self.s.rollback()
            raise CloseConflictError("Variance review version is stale")
        self.s.expire(review)
        self.s.refresh(review)
        self.close._audit(
            AuditAction.UPDATE,
            "VarianceReview",
            review.id,
            before=before,
            after={"disposition": review.disposition.value, "version": review.version},
            event="variance_disposition_updated",
        )
        self.s.commit()
        self.s.refresh(review)
        return review

    def _validate_journal_reference(
        self,
        cycle_id: int,
        transaction_id: int | None,
        staged_transaction_id: int | None,
    ) -> None:
        if (transaction_id is None) == (staged_transaction_id is None):
            raise CloseValidationError("Exactly one posted or staged transaction reference is required")
        _, period = self._cycle_and_period(cycle_id)
        if transaction_id is not None:
            transaction = self.s.exec(
                select(Transaction).where(
                    Transaction.organization_id == self.organization_id,
                    Transaction.id == transaction_id,
                )
            ).first()
            if transaction is None or not period.start_date <= transaction.date <= period.end_date:
                raise CloseNotFoundError("Journal transaction not found")
            return
        staged = self.s.get(StagedTransaction, staged_transaction_id)
        if staged is None or not period.start_date <= staged.date <= period.end_date:
            raise CloseNotFoundError("Staged transaction not found")
        marker = staged.source_metadata.get("_organization_id")
        if marker is not None and marker != self.organization_id:
            raise CloseNotFoundError("Staged transaction not found")
        if marker is None:
            account_ids = list(
                self.s.exec(
                    select(StagedPosting.account_id).where(StagedPosting.staged_transaction_id == staged_transaction_id)
                )
            )
            for account_id in account_ids:
                if account_id is None:
                    raise CloseNotFoundError("Staged transaction not found")
                account = self.s.get(Account, account_id)
                if account is None or account.organization_id != self.organization_id:
                    raise CloseNotFoundError("Staged transaction not found")

    def request_approval(
        self,
        cycle_id: int,
        *,
        transaction_id: int | None = None,
        staged_transaction_id: int | None = None,
        reason: str | None = None,
    ) -> JournalApproval:
        cycle, _ = self._cycle_and_period(cycle_id, mutation="Journal approval request")
        self._validate_journal_reference(cycle_id, transaction_id, staged_transaction_id)
        reference_key = (
            f"transaction:{transaction_id}" if transaction_id is not None else f"staged:{staged_transaction_id}"
        )
        stmt = select(JournalApproval).where(
            JournalApproval.organization_id == self.organization_id,
            JournalApproval.cycle_id == cycle_id,
            JournalApproval.reference_key == reference_key,
        )
        existing = self.s.exec(stmt).first()
        if existing is not None and existing.status in {
            JournalApprovalStatus.REQUESTED,
            JournalApprovalStatus.APPROVED,
        }:
            return existing
        now = self._now()
        if existing is not None:
            before_status = existing.status
            old_version = existing.version
            self.close.bump_content_revision(cycle)
            result = self.s.exec(
                update(JournalApproval)
                .where(
                    cast(Any, JournalApproval.id) == existing.id,
                    cast(Any, JournalApproval.organization_id) == self.organization_id,
                    cast(Any, JournalApproval.cycle_id) == cycle_id,
                    cast(Any, JournalApproval.version) == old_version,
                )
                .values(
                    status=JournalApprovalStatus.REQUESTED,
                    requestor_user_id=self.actor_user_id,
                    requested_at=now,
                    decided_by_id=None,
                    decided_at=None,
                    reason=reason.strip() if reason else None,
                    version=old_version + 1,
                    updated_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            if getattr(result, "rowcount", 0) != 1:
                self.s.rollback()
                raise CloseConflictError("Journal approval version is stale")
            self.s.add(
                JournalApprovalDecision(
                    organization_id=self.organization_id,
                    approval_id=cast(int, existing.id),
                    from_status=before_status,
                    to_status=JournalApprovalStatus.REQUESTED,
                    decided_by_id=self.actor_user_id,
                    decided_at=now,
                    reason=reason.strip() if reason else None,
                )
            )
            self.s.expire(existing)
            self.s.refresh(existing)
            self.close._audit(
                AuditAction.UPDATE,
                "JournalApproval",
                existing.id,
                before={"status": before_status.value, "version": old_version},
                after={"status": existing.status.value, "version": existing.version},
                event="journal_approval_rerequested",
            )
            self.s.commit()
            self.s.refresh(existing)
            return existing
        approval = JournalApproval(
            organization_id=self.organization_id,
            cycle_id=cycle_id,
            reference_key=reference_key,
            transaction_id=transaction_id,
            staged_transaction_id=staged_transaction_id,
            requestor_user_id=self.actor_user_id,
            reason=reason.strip() if reason else None,
        )
        self.s.add(approval)
        try:
            self.s.flush()
            self.close.bump_content_revision(cycle)
        except IntegrityError as exc:
            self.s.rollback()
            raise CloseConflictError("A current approval already exists for this journal") from exc
        self.close._audit(
            AuditAction.CREATE,
            "JournalApproval",
            approval.id,
            after={
                "cycle_id": cycle_id,
                "transaction_id": transaction_id,
                "staged_transaction_id": staged_transaction_id,
                "status": approval.status.value,
            },
            event="journal_approval_requested",
        )
        self.s.commit()
        self.s.refresh(approval)
        return approval

    def decide_approval(
        self,
        cycle_id: int,
        approval_id: int,
        *,
        version: int,
        decision: JournalApprovalStatus,
        reason: str | None,
        is_admin: bool = False,
    ) -> JournalApproval:
        cycle, _ = self._cycle_and_period(cycle_id, mutation="Journal approval decision")
        approval = self.s.exec(
            select(JournalApproval).where(
                JournalApproval.organization_id == self.organization_id,
                JournalApproval.cycle_id == cycle_id,
                JournalApproval.id == approval_id,
            )
        ).first()
        if approval is None:
            raise CloseNotFoundError("Journal approval not found")
        if approval.status == decision:
            return approval
        if approval.version != version:
            raise CloseConflictError("Journal approval version is stale")
        if approval.requestor_user_id == self.actor_user_id and decision == JournalApprovalStatus.APPROVED:
            raise CloseConflictError("A journal approval requestor cannot approve their own request")
        allowed = {
            JournalApprovalStatus.REQUESTED: {JournalApprovalStatus.APPROVED, JournalApprovalStatus.REJECTED},
            JournalApprovalStatus.APPROVED: {JournalApprovalStatus.REVOKED},
        }
        if decision not in allowed.get(approval.status, set()):
            raise CloseConflictError(f"Cannot change approval from {approval.status.value} to {decision.value}")
        if decision == JournalApprovalStatus.REVOKED and not is_admin:
            raise CloseConflictError("Administrator access is required to revoke an approval")
        normalized_reason = reason.strip() if reason else None
        if decision in {JournalApprovalStatus.REJECTED, JournalApprovalStatus.REVOKED} and not normalized_reason:
            raise CloseValidationError("A reason is required to reject or revoke a journal approval")
        before_status = approval.status
        now = self._now()
        history = JournalApprovalDecision(
            organization_id=self.organization_id,
            approval_id=cast(int, approval.id),
            from_status=before_status,
            to_status=decision,
            decided_by_id=self.actor_user_id,
            decided_at=now,
            reason=normalized_reason,
        )
        self.close.bump_content_revision(cycle)
        result = self.s.exec(
            update(JournalApproval)
            .where(
                cast(Any, JournalApproval.id) == approval_id,
                cast(Any, JournalApproval.organization_id) == self.organization_id,
                cast(Any, JournalApproval.cycle_id) == cycle_id,
                cast(Any, JournalApproval.version) == version,
                cast(Any, JournalApproval.status) == before_status,
            )
            .values(
                status=decision,
                decided_by_id=self.actor_user_id,
                decided_at=now,
                reason=normalized_reason,
                version=version + 1,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if getattr(result, "rowcount", 0) != 1:
            self.s.rollback()
            raise CloseConflictError("Journal approval version is stale")
        self.s.add(history)
        self.s.expire(approval)
        self.s.refresh(approval)
        self.close._audit(
            AuditAction.UPDATE,
            "JournalApproval",
            approval.id,
            before={"status": before_status.value, "version": version},
            after={"status": decision.value, "version": approval.version},
            event="journal_approval_decided",
        )
        self.s.commit()
        self.s.refresh(approval)
        return approval

    def list_approvals(self, cycle_id: int) -> list[JournalApproval]:
        self.close.require_cycle(cycle_id)
        return list(
            self.s.exec(
                select(JournalApproval)
                .where(JournalApproval.organization_id == self.organization_id, JournalApproval.cycle_id == cycle_id)
                .order_by(cast(Any, JournalApproval.id))
            )
        )

    def approval_history(self, approval_id: int) -> list[JournalApprovalDecision]:
        return list(
            self.s.exec(
                select(JournalApprovalDecision)
                .where(
                    JournalApprovalDecision.organization_id == self.organization_id,
                    JournalApprovalDecision.approval_id == approval_id,
                )
                .order_by(cast(Any, JournalApprovalDecision.id))
            )
        )


__all__ = ["ReconciliationService"]
