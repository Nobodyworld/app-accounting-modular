"""Accountant close lifecycle, checklist, and readiness services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from ..audit import get_current_actor
from ..limits import MAX_CUSTOM_CLOSE_TASKS, MAX_TRANSITION_REASON_LENGTH
from ..models.models import (
    Account,
    AccountingPeriod,
    AccountingPeriodStatus,
    AccountReconciliation,
    AccountType,
    AuditAction,
    AuditLog,
    CloseChecklistTask,
    CloseCycle,
    CloseCycleStatus,
    CloseEvidence,
    CloseTaskControlType,
    CloseTaskStatus,
    JournalApproval,
    JournalApprovalStatus,
    Membership,
    Organization,
    ReconciliationStatus,
    StagedPosting,
    StagedTransaction,
    Transaction,
    User,
    VarianceDisposition,
    VarianceReview,
    VarianceReviewRun,
    WorkflowStatus,
)
from .ledger_service import LedgerService


class CloseDomainError(ValueError):
    code = "CLOSE_DOMAIN_ERROR"


class CloseNotFoundError(CloseDomainError):
    code = "CLOSE_NOT_FOUND"


class CloseConflictError(CloseDomainError):
    code = "CLOSE_CONFLICT"


class CloseValidationError(CloseDomainError):
    code = "CLOSE_VALIDATION"


@dataclass(frozen=True, slots=True)
class ReadinessBlocker:
    code: str
    category: str
    message: str
    source_entity_type: str
    source_entity_id: str | None
    recommended_action: str


@dataclass(frozen=True, slots=True)
class CloseReadiness:
    cycle_id: int
    cycle_status: CloseCycleStatus
    period_status: AccountingPeriodStatus
    state: str
    required_task_count: int
    completed_required_count: int
    completion_ratio: Decimal
    blocker_count: int
    warning_count: int
    blockers: tuple[ReadinessBlocker, ...]
    warnings: tuple[ReadinessBlocker, ...]
    evidence_freshness: str
    version: int
    content_revision: int
    ledger_activity_revision: int
    effective_task_statuses: dict[str, CloseTaskStatus]
    latest_variance_run_id: int | None
    latest_variance_run_row_count: int | None
    latest_variance_run_ledger_activity_revision: int | None


DEFAULT_CLOSE_POLICY: dict[str, Any] = {
    "required_reconciliation_account_ids": [],
    "reconciliation_scope_not_applicable": False,
    "variance_review_required": True,
    "journal_approval_mode": "REQUESTED_ONLY",
    "override_reason": None,
    "overridden_by_user_id": None,
}

_POLICY_OVERRIDE_FIELDS = {
    "required_reconciliation_account_ids",
    "reconciliation_scope_not_applicable",
    "variance_review_required",
    "journal_approval_mode",
    "override_reason",
}


def safe_close_policy(policy: dict[str, Any]) -> dict[str, Any]:
    """Return only the typed, evidence-safe policy contract."""

    return {
        "required_reconciliation_account_ids": [
            int(account_id) for account_id in policy.get("required_reconciliation_account_ids", [])
        ],
        "reconciliation_scope_not_applicable": bool(policy.get("reconciliation_scope_not_applicable", False)),
        "variance_review_required": bool(policy.get("variance_review_required", True)),
        "journal_approval_mode": str(policy.get("journal_approval_mode", "REQUESTED_ONLY")),
        "override_reason": policy.get("override_reason"),
        "overridden_by_user_id": policy.get("overridden_by_user_id"),
    }


OPERATIONAL_CYCLE_STATES = {CloseCycleStatus.IN_PROGRESS, CloseCycleStatus.BLOCKED}

DEFAULT_CHECKLIST: tuple[tuple[str, str, str, CloseTaskControlType], ...] = (
    (
        "staged_journal_exceptions_resolved",
        "Staged journal exceptions resolved",
        "workflow",
        CloseTaskControlType.SYSTEM,
    ),
    ("trial_balance_balanced", "Trial balance balanced", "ledger", CloseTaskControlType.SYSTEM),
    (
        "required_reconciliations_complete",
        "Required reconciliations complete",
        "reconciliations",
        CloseTaskControlType.SYSTEM,
    ),
    (
        "material_variances_reviewed",
        "Material variances reviewed",
        "variance_review",
        CloseTaskControlType.SYSTEM,
    ),
    (
        "required_journal_approvals_complete",
        "Required journal approvals complete",
        "journal_approvals",
        CloseTaskControlType.SYSTEM,
    ),
    (
        "provider_and_report_freshness_reviewed",
        "Provider and report freshness reviewed",
        "evidence",
        CloseTaskControlType.ATTESTATION,
    ),
    ("close_evidence_generated", "Close evidence generated", "evidence", CloseTaskControlType.SYSTEM),
    (
        "final_close_approved",
        "Final close approved",
        "close",
        CloseTaskControlType.ADMIN_APPROVAL,
    ),
)


class CloseService:
    """Single authoritative service boundary for period and close transitions."""

    def __init__(self, session: Session, organization_id: int, actor_user_id: int):
        self.s = session
        self.organization_id = organization_id
        self.actor_user_id = actor_user_id

    @staticmethod
    def _id(value: int | None, label: str) -> int:
        if value is None:
            raise CloseValidationError(f"{label} is missing an identifier")
        return value

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    def _audit(
        self,
        action: AuditAction,
        entity_name: str,
        entity_id: int | None,
        *,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        event: str,
    ) -> None:
        actor = get_current_actor()
        before_map = before or {}
        after_map = after or {}
        diff = {
            key: {"before": before_map.get(key), "after": after_map.get(key)}
            for key in sorted(set(before_map) | set(after_map))
            if before_map.get(key) != after_map.get(key)
        }
        self.s.add(
            AuditLog(
                ts=self._now(),
                action=action,
                entity_name=entity_name,
                entity_id=str(entity_id) if entity_id is not None else None,
                before_state=before,
                after_state=after,
                payload_diff=diff or None,
                request_id=actor.request_id if actor else str(uuid4()),
                actor_user_id=self.actor_user_id,
                actor_org_id=self.organization_id,
                actor_label=actor.user_label if actor else None,
                source=actor.source if actor else "service",
                context={"event": event},
            )
        )

    def require_period(self, period_id: int) -> AccountingPeriod:
        period = self.s.exec(
            select(AccountingPeriod).where(
                AccountingPeriod.organization_id == self.organization_id,
                AccountingPeriod.id == period_id,
            )
        ).first()
        if period is None:
            raise CloseNotFoundError("Accounting period not found")
        return period

    def require_cycle(self, cycle_id: int) -> CloseCycle:
        cycle = self.s.exec(
            select(CloseCycle).where(
                CloseCycle.organization_id == self.organization_id,
                CloseCycle.id == cycle_id,
            )
        ).first()
        if cycle is None:
            raise CloseNotFoundError("Close cycle not found")
        return cycle

    def require_cycle_mutation(
        self,
        cycle_id: int,
        *,
        allowed: set[CloseCycleStatus],
        operation: str,
    ) -> CloseCycle:
        """Enforce the lifecycle write policy at the shared service boundary."""

        cycle = self.require_cycle(cycle_id)
        if cycle.status not in allowed:
            raise CloseConflictError(f"{operation} is not allowed while the close cycle is {cycle.status.value}")
        return cycle

    def validate_owner(self, user_id: int | None) -> int | None:
        """Resolve an active same-tenant assignee without disclosing foreign identities."""

        if user_id is None:
            return None
        user = self.s.exec(select(User).where(User.id == user_id, cast(Any, User.is_active).is_(True))).first()
        organization = self.s.exec(
            select(Organization).where(
                Organization.id == self.organization_id,
                cast(Any, Organization.is_active).is_(True),
            )
        ).first()
        membership = self.s.exec(
            select(Membership).where(
                Membership.user_id == user_id,
                Membership.organization_id == self.organization_id,
            )
        ).first()
        if user is None or organization is None or membership is None:
            raise CloseNotFoundError("Close assignment user not found")
        return user_id

    def require_admin_actor(self) -> None:
        membership = self.s.exec(
            select(Membership).where(
                Membership.user_id == self.actor_user_id,
                Membership.organization_id == self.organization_id,
                cast(Any, Membership.is_admin).is_(True),
            )
        ).first()
        if membership is None:
            raise CloseConflictError("Organization administrator access is required for this transition")

    def bump_content_revision(self, cycle: CloseCycle) -> int:
        """Atomically invalidate evidence for a successful in-transaction mutation."""

        cycle_id = self._id(cycle.id, "close cycle")
        expected = cycle.content_revision
        result = self.s.exec(
            update(CloseCycle)
            .where(
                cast(Any, CloseCycle.id) == cycle_id,
                cast(Any, CloseCycle.organization_id) == self.organization_id,
                cast(Any, CloseCycle.content_revision) == expected,
            )
            .values(
                content_revision=expected + 1,
                updated_at=self._now(),
                updated_by_id=self.actor_user_id,
            )
            .execution_options(synchronize_session=False)
        )
        if getattr(result, "rowcount", 0) != 1:
            self.s.rollback()
            raise CloseConflictError("Close cycle content revision is stale")
        self.s.expire(cycle)
        self.s.refresh(cycle)
        return cycle.content_revision

    def create_period(self, label: str, start_date: date, end_date: date) -> AccountingPeriod:
        from .period_lock import acquire_period_write_gate

        normalized = label.strip()
        if not normalized:
            raise CloseValidationError("Period label is required")
        if start_date > end_date:
            raise CloseValidationError("Period start date must not be after end date")
        acquire_period_write_gate(self.s, self.organization_id)
        overlap = self.s.exec(
            select(AccountingPeriod).where(
                AccountingPeriod.organization_id == self.organization_id,
                AccountingPeriod.status == AccountingPeriodStatus.OPEN,
                cast(Any, AccountingPeriod.start_date) <= end_date,
                cast(Any, AccountingPeriod.end_date) >= start_date,
            )
        ).first()
        if overlap is not None:
            raise CloseConflictError("Accounting period overlaps an active period")
        now = self._now()
        period = AccountingPeriod(
            organization_id=self.organization_id,
            label=normalized,
            start_date=start_date,
            end_date=end_date,
            created_by_id=self.actor_user_id,
            updated_by_id=self.actor_user_id,
            created_at=now,
            updated_at=now,
        )
        self.s.add(period)
        try:
            self.s.flush()
            self._audit(
                AuditAction.CREATE,
                "AccountingPeriod",
                period.id,
                after={"label": period.label, "start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
                event="period_created",
            )
            self.s.commit()
        except IntegrityError as exc:
            self.s.rollback()
            raise CloseConflictError("Accounting period label already exists") from exc
        self.s.refresh(period)
        return period

    def list_periods(self, *, limit: int = 100, offset: int = 0) -> list[AccountingPeriod]:
        return list(
            self.s.exec(
                select(AccountingPeriod)
                .where(AccountingPeriod.organization_id == self.organization_id)
                .order_by(cast(Any, AccountingPeriod.start_date).desc(), cast(Any, AccountingPeriod.id).desc())
                .offset(offset)
                .limit(limit)
            )
        )

    def create_cycle(
        self,
        period_id: int,
        name: str,
        *,
        owner_user_id: int | None = None,
        due_date: date | None = None,
        policy: dict[str, Any] | None = None,
        notes: str | None = None,
    ) -> CloseCycle:
        period = self.require_period(period_id)
        if period.status == AccountingPeriodStatus.CLOSED:
            raise CloseConflictError("Cannot create a new close cycle for a closed period")
        existing = self.s.exec(select(CloseCycle).where(CloseCycle.period_id == period_id)).first()
        if existing is not None:
            raise CloseConflictError("A close cycle already exists for this period")
        normalized_name = name.strip()
        if not normalized_name:
            raise CloseValidationError("Close cycle name is required")
        requested_owner = owner_user_id or self.actor_user_id
        self.validate_owner(requested_owner)
        required_accounts = list(
            self.s.exec(
                select(Account.id)
                .where(
                    Account.organization_id == self.organization_id,
                    cast(Any, Account.type).in_([AccountType.ASSET, AccountType.LIABILITY, AccountType.EQUITY]),
                )
                .order_by(cast(Any, Account.id))
            )
        )
        policy_override = dict(policy or {})
        unknown_policy_fields = sorted(set(policy_override) - _POLICY_OVERRIDE_FIELDS)
        if unknown_policy_fields:
            raise CloseValidationError(f"Unknown close policy field(s): {', '.join(unknown_policy_fields)}")
        if policy_override:
            self.require_admin_actor()
            reason_value = policy_override.get("override_reason")
            reason = reason_value.strip() if isinstance(reason_value, str) else ""
            if not reason:
                raise CloseValidationError("A nonempty policy override reason is required")
            if len(reason) > MAX_TRANSITION_REASON_LENGTH:
                raise CloseValidationError("Policy override reason exceeds the maximum length")
            policy_override["override_reason"] = reason

        merged_policy = {
            **DEFAULT_CLOSE_POLICY,
            "required_reconciliation_account_ids": [
                int(account_id) for account_id in required_accounts if account_id is not None
            ],
            "reconciliation_scope_not_applicable": not required_accounts,
            **policy_override,
        }
        approval_mode = merged_policy.get("journal_approval_mode")
        if approval_mode not in {"REQUESTED_ONLY", "ALL_PERIOD_TRANSACTIONS"}:
            raise CloseValidationError("journal_approval_mode must be REQUESTED_ONLY or ALL_PERIOD_TRANSACTIONS")
        requested_scope = merged_policy.get("required_reconciliation_account_ids", [])
        if not isinstance(requested_scope, list) or any(
            not isinstance(account_id, int) or isinstance(account_id, bool) or account_id < 1
            for account_id in requested_scope
        ):
            raise CloseValidationError("required_reconciliation_account_ids must contain positive account IDs")
        allowed_scope = {int(account_id) for account_id in required_accounts if account_id is not None}
        if not set(requested_scope).issubset(allowed_scope):
            raise CloseNotFoundError("Required reconciliation account not found")
        merged_policy["required_reconciliation_account_ids"] = sorted(set(requested_scope))
        if not isinstance(merged_policy.get("variance_review_required"), bool):
            raise CloseValidationError("variance_review_required must be a boolean")
        not_applicable = merged_policy.get("reconciliation_scope_not_applicable")
        if not isinstance(not_applicable, bool):
            raise CloseValidationError("reconciliation_scope_not_applicable must be a boolean")
        if not_applicable and merged_policy["required_reconciliation_account_ids"]:
            raise CloseValidationError("A not-applicable reconciliation policy cannot also require accounts")
        if not not_applicable and not merged_policy["required_reconciliation_account_ids"]:
            raise CloseValidationError("An empty reconciliation scope requires a not-applicable policy")
        merged_policy["overridden_by_user_id"] = self.actor_user_id if policy_override else None
        merged_policy = safe_close_policy(merged_policy)
        now = self._now()
        cycle = CloseCycle(
            organization_id=self.organization_id,
            period_id=period_id,
            name=normalized_name,
            owner_user_id=requested_owner,
            due_date=due_date,
            policy=merged_policy,
            notes=notes.strip() if notes else None,
            created_by_id=self.actor_user_id,
            updated_by_id=self.actor_user_id,
            created_at=now,
            updated_at=now,
        )
        self.s.add(cycle)
        try:
            self.s.flush()
            cycle_id = self._id(cycle.id, "close cycle")
            for order, (key, title, category, control_type) in enumerate(DEFAULT_CHECKLIST, start=1):
                self.s.add(
                    CloseChecklistTask(
                        organization_id=self.organization_id,
                        cycle_id=cycle_id,
                        task_key=key,
                        title=title,
                        description=f"Controlled close task: {title}.",
                        category=category,
                        required=True,
                        control_type=control_type,
                        owner_user_id=cycle.owner_user_id,
                        due_date=due_date,
                        sort_order=order * 10,
                    )
                )
            self._audit(
                AuditAction.CREATE,
                "CloseCycle",
                cycle.id,
                after={"status": cycle.status.value, "period_id": period_id, "policy": merged_policy},
                event="cycle_created",
            )
            self.s.commit()
        except IntegrityError as exc:
            self.s.rollback()
            raise CloseConflictError("A close cycle already exists for this period") from exc
        self.s.refresh(cycle)
        return cycle

    def list_cycles(self, period_id: int) -> list[CloseCycle]:
        """Return tenant-scoped cycles for a period in stable order."""

        self.require_period(period_id)
        return list(
            self.s.exec(
                select(CloseCycle)
                .where(
                    CloseCycle.organization_id == self.organization_id,
                    CloseCycle.period_id == period_id,
                )
                .order_by(cast(Any, CloseCycle.id))
            )
        )

    def _transition(
        self,
        cycle: CloseCycle,
        *,
        expected: set[CloseCycleStatus],
        target: CloseCycleStatus,
        version: int,
        event: str,
        reason: str | None = None,
    ) -> CloseCycle:
        if cycle.version != version:
            raise CloseConflictError("Close cycle version is stale")
        if cycle.status not in expected:
            raise CloseConflictError(f"Cannot transition close cycle from {cycle.status.value} to {target.value}")
        before = {"status": cycle.status.value, "version": cycle.version}
        now = self._now()
        result = self.s.exec(
            update(CloseCycle)
            .where(
                cast(Any, CloseCycle.id) == cycle.id,
                cast(Any, CloseCycle.organization_id) == self.organization_id,
                cast(Any, CloseCycle.version) == version,
                cast(Any, CloseCycle.content_revision) == cycle.content_revision,
            )
            .values(
                status=target,
                version=version + 1,
                content_revision=cycle.content_revision + 1,
                updated_at=now,
                updated_by_id=self.actor_user_id,
                last_reason=reason,
            )
            .execution_options(synchronize_session=False)
        )
        if getattr(result, "rowcount", 0) != 1:
            self.s.rollback()
            raise CloseConflictError("Close cycle version is stale")
        self.s.expire(cycle)
        self.s.refresh(cycle)
        self._audit(
            AuditAction.UPDATE,
            "CloseCycle",
            cycle.id,
            before=before,
            after={
                "status": target.value,
                "version": cycle.version,
                "content_revision": cycle.content_revision,
                "reason": reason,
            },
            event=event,
        )
        return cycle

    def start(self, cycle_id: int, version: int) -> CloseCycle:
        cycle = self.require_cycle(cycle_id)
        self._transition(
            cycle,
            expected={CloseCycleStatus.DRAFT},
            target=CloseCycleStatus.IN_PROGRESS,
            version=version,
            event="cycle_started",
        )
        cycle.started_at = self._now()
        self.s.commit()
        self.s.refresh(cycle)
        return cycle

    def mark_ready(self, cycle_id: int, version: int) -> CloseCycle:
        cycle = self.require_cycle(cycle_id)
        readiness = self.readiness(cycle_id)
        if readiness.blocker_count:
            raise CloseConflictError("Close cycle still has readiness blockers")
        self._transition(
            cycle,
            expected={CloseCycleStatus.IN_PROGRESS, CloseCycleStatus.BLOCKED},
            target=CloseCycleStatus.READY_FOR_APPROVAL,
            version=version,
            event="cycle_marked_ready",
        )
        cycle.readiness_at = self._now()
        self.s.commit()
        self.s.refresh(cycle)
        return cycle

    def close(self, cycle_id: int, version: int) -> CloseCycle:
        from .close_evidence_service import CloseEvidenceService
        from .period_lock import acquire_period_write_gate

        self.require_admin_actor()
        acquire_period_write_gate(self.s, self.organization_id)
        cycle = self.require_cycle(cycle_id)
        if cycle.status != CloseCycleStatus.READY_FOR_APPROVAL:
            raise CloseConflictError("Close cycle must be ready for approval before final close")
        readiness = self.readiness(cycle_id)
        if readiness.blocker_count:
            raise CloseConflictError("Close cycle readiness changed and final close is blocked")
        period = self.require_period(cycle.period_id)
        try:
            self._transition(
                cycle,
                expected={CloseCycleStatus.READY_FOR_APPROVAL},
                target=CloseCycleStatus.CLOSED,
                version=version,
                event="cycle_closed",
            )
            now = self._now()
            cycle.closed_at = now
            cycle.approved_at = now
            period.status = AccountingPeriodStatus.CLOSED
            period.version += 1
            period.updated_at = now
            period.updated_by_id = self.actor_user_id
            period.closed_at = now
            period.closed_by_id = self.actor_user_id
            self.s.add(cycle)
            self.s.add(period)
            self._audit(
                AuditAction.UPDATE,
                "AccountingPeriod",
                period.id,
                before={"status": AccountingPeriodStatus.OPEN.value},
                after={"status": AccountingPeriodStatus.CLOSED.value, "cycle_id": cycle.id},
                event="period_closed",
            )
            self.s.flush()
            evidence_service = CloseEvidenceService(self.s, self.organization_id, self.actor_user_id)
            bundle = evidence_service.build_bundle(cycle_id)
            evidence_service.record_generation(
                cycle_id,
                bundle,
                summary="Final closed-period evidence",
                commit=False,
                allow_closed=True,
            )
            self.s.commit()
        except Exception:
            self.s.rollback()
            raise
        self.s.refresh(cycle)
        return cycle

    def reopen(self, cycle_id: int, version: int, reason: str) -> CloseCycle:
        from .period_lock import acquire_period_write_gate

        normalized = reason.strip()
        if not normalized:
            raise CloseValidationError("A nonempty reopen reason is required")
        self.require_admin_actor()
        acquire_period_write_gate(self.s, self.organization_id)
        cycle = self.require_cycle(cycle_id)
        period = self.require_period(cycle.period_id)
        overlap = self.s.exec(
            select(AccountingPeriod).where(
                AccountingPeriod.organization_id == self.organization_id,
                AccountingPeriod.id != period.id,
                AccountingPeriod.status == AccountingPeriodStatus.OPEN,
                cast(Any, AccountingPeriod.start_date) <= period.end_date,
                cast(Any, AccountingPeriod.end_date) >= period.start_date,
            )
        ).first()
        if overlap is not None:
            raise CloseConflictError("Accounting period overlaps an active period")
        self._transition(
            cycle,
            expected={CloseCycleStatus.CLOSED},
            target=CloseCycleStatus.IN_PROGRESS,
            version=version,
            event="cycle_reopened",
            reason=normalized,
        )
        now = self._now()
        cycle.reopened_at = now
        cycle.closed_at = None
        cycle.readiness_at = None
        cycle.approved_at = None
        period.status = AccountingPeriodStatus.OPEN
        period.version += 1
        period.updated_at = now
        period.updated_by_id = self.actor_user_id
        period.reopened_at = now
        period.reopened_by_id = self.actor_user_id
        self.s.add(period)
        self._audit(
            AuditAction.UPDATE,
            "AccountingPeriod",
            period.id,
            before={"status": AccountingPeriodStatus.CLOSED.value},
            after={"status": AccountingPeriodStatus.OPEN.value, "reason": normalized},
            event="period_reopened",
        )
        self.s.commit()
        self.s.refresh(cycle)
        return cycle

    def return_to_work(self, cycle_id: int, version: int, reason: str) -> CloseCycle:
        normalized = reason.strip()
        if not normalized:
            raise CloseValidationError("A nonempty return-to-work reason is required")
        self.require_admin_actor()
        cycle = self.require_cycle(cycle_id)
        self._transition(
            cycle,
            expected={CloseCycleStatus.READY_FOR_APPROVAL},
            target=CloseCycleStatus.IN_PROGRESS,
            version=version,
            event="cycle_returned_to_work",
            reason=normalized,
        )
        cycle.readiness_at = None
        cycle.approved_at = None
        self.s.commit()
        self.s.refresh(cycle)
        return cycle

    def cancel(self, cycle_id: int, version: int, reason: str) -> CloseCycle:
        normalized = reason.strip()
        if not normalized:
            raise CloseValidationError("A nonempty cancellation reason is required")
        self.require_admin_actor()
        cycle = self.require_cycle(cycle_id)
        self._transition(
            cycle,
            expected={CloseCycleStatus.DRAFT, CloseCycleStatus.IN_PROGRESS, CloseCycleStatus.BLOCKED},
            target=CloseCycleStatus.CANCELLED,
            version=version,
            event="cycle_cancelled",
            reason=normalized,
        )
        cycle.cancelled_at = self._now()
        self.s.commit()
        self.s.refresh(cycle)
        return cycle

    def restart(self, cycle_id: int, version: int, reason: str) -> CloseCycle:
        normalized = reason.strip()
        if not normalized:
            raise CloseValidationError("A nonempty restart reason is required")
        self.require_admin_actor()
        cycle = self.require_cycle(cycle_id)
        period = self.require_period(cycle.period_id)
        if period.status != AccountingPeriodStatus.OPEN:
            raise CloseConflictError("A cancelled close cycle can restart only while its period is open")
        self._transition(
            cycle,
            expected={CloseCycleStatus.CANCELLED},
            target=CloseCycleStatus.IN_PROGRESS,
            version=version,
            event="cycle_restarted",
            reason=normalized,
        )
        cycle.cancelled_at = None
        cycle.started_at = cycle.started_at or self._now()
        self.s.commit()
        self.s.refresh(cycle)
        return cycle

    def list_checklist(self, cycle_id: int) -> list[CloseChecklistTask]:
        self.require_cycle(cycle_id)
        return list(
            self.s.exec(
                select(CloseChecklistTask)
                .where(
                    CloseChecklistTask.organization_id == self.organization_id,
                    CloseChecklistTask.cycle_id == cycle_id,
                )
                .order_by(cast(Any, CloseChecklistTask.sort_order), cast(Any, CloseChecklistTask.id))
            )
        )

    def create_custom_task(
        self,
        cycle_id: int,
        *,
        title: str,
        description: str = "",
        category: str = "custom",
        required: bool = False,
        owner_user_id: int | None = None,
        due_date: date | None = None,
        notes: str | None = None,
    ) -> CloseChecklistTask:
        cycle = self.require_cycle_mutation(
            cycle_id,
            allowed={CloseCycleStatus.DRAFT, *OPERATIONAL_CYCLE_STATES},
            operation="Checklist configuration",
        )
        self.validate_owner(owner_user_id)
        existing = self.list_checklist(cycle_id)
        custom_count = sum(task.control_type == CloseTaskControlType.CUSTOM for task in existing)
        if custom_count >= MAX_CUSTOM_CLOSE_TASKS:
            raise CloseValidationError("Maximum custom close tasks reached")
        normalized = title.strip()
        if not normalized:
            raise CloseValidationError("Checklist title is required")
        key = f"custom_{uuid4().hex}"
        task = CloseChecklistTask(
            organization_id=self.organization_id,
            cycle_id=cycle_id,
            task_key=key,
            title=normalized,
            description=description.strip(),
            category=category.strip() or "custom",
            required=required,
            control_type=CloseTaskControlType.CUSTOM,
            owner_user_id=owner_user_id,
            due_date=due_date,
            notes=notes.strip() if notes else None,
            sort_order=(max((item.sort_order for item in existing), default=0) + 10),
        )
        self.s.add(task)
        self.s.flush()
        self.bump_content_revision(cycle)
        self._audit(
            AuditAction.CREATE,
            "CloseChecklistTask",
            task.id,
            after={"cycle_id": cycle_id, "task_key": key, "required": required},
            event="checklist_task_created",
        )
        self.s.commit()
        self.s.refresh(task)
        return task

    def update_manual_task(
        self,
        cycle_id: int,
        task_id: int,
        *,
        version: int,
        complete: bool,
        notes: str | None = None,
        owner_user_id: int | None = None,
        due_date: date | None = None,
        is_admin: bool = False,
    ) -> CloseChecklistTask:
        cycle = self.require_cycle_mutation(
            cycle_id,
            allowed=OPERATIONAL_CYCLE_STATES,
            operation="Checklist update",
        )
        self.validate_owner(owner_user_id)
        task = self.s.exec(
            select(CloseChecklistTask).where(
                CloseChecklistTask.organization_id == self.organization_id,
                CloseChecklistTask.cycle_id == cycle_id,
                CloseChecklistTask.id == task_id,
            )
        ).first()
        if task is None:
            raise CloseNotFoundError("Checklist task not found")
        if task.control_type == CloseTaskControlType.SYSTEM:
            raise CloseConflictError("System-derived checklist tasks cannot be completed manually")
        if task.task_key == "final_close_approved":
            raise CloseConflictError("Final close approval is completed only by the administrator final-close action")
        if task.control_type == CloseTaskControlType.ADMIN_APPROVAL and not is_admin:
            raise CloseConflictError("Administrator approval is required for this task")
        before = {"status": task.status.value, "version": task.version}
        now = self._now()
        result = self.s.exec(
            update(CloseChecklistTask)
            .where(
                cast(Any, CloseChecklistTask.id) == task_id,
                cast(Any, CloseChecklistTask.organization_id) == self.organization_id,
                cast(Any, CloseChecklistTask.cycle_id) == cycle_id,
                cast(Any, CloseChecklistTask.version) == version,
            )
            .values(
                status=CloseTaskStatus.COMPLETE if complete else CloseTaskStatus.PENDING,
                completed_by_id=self.actor_user_id if complete else None,
                completed_at=now if complete else None,
                notes=notes.strip() if notes else None,
                owner_user_id=owner_user_id,
                due_date=due_date,
                version=version + 1,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if getattr(result, "rowcount", 0) != 1:
            self.s.rollback()
            raise CloseConflictError("Checklist task version is stale")
        self.bump_content_revision(cycle)
        self.s.expire(task)
        self.s.refresh(task)
        self._audit(
            AuditAction.UPDATE,
            "CloseChecklistTask",
            task.id,
            before=before,
            after={"status": task.status.value, "version": task.version},
            event="checklist_task_updated",
        )
        self.s.commit()
        self.s.refresh(task)
        return task

    def _staged_belongs_to_org(self, staged: StagedTransaction) -> bool:
        marker = staged.source_metadata.get("_organization_id")
        if marker is not None:
            return bool(marker == self.organization_id)
        if staged.transaction_id is not None:
            transaction = self.s.get(Transaction, staged.transaction_id)
            return transaction is not None and transaction.organization_id == self.organization_id
        staged_id = self._id(staged.id, "staged transaction")
        posting_ids = list(
            self.s.exec(select(StagedPosting.account_id).where(StagedPosting.staged_transaction_id == staged_id))
        )
        if not posting_ids:
            return False
        from ..models.models import Account

        org_ids = {
            account.organization_id
            for account_id in posting_ids
            if account_id is not None and (account := self.s.get(Account, account_id)) is not None
        }
        return org_ids == {self.organization_id}

    def readiness(self, cycle_id: int) -> CloseReadiness:
        cycle = self.require_cycle(cycle_id)
        period = self.require_period(cycle.period_id)
        blockers: list[ReadinessBlocker] = []
        warnings: list[ReadinessBlocker] = []
        completed_system_keys: set[str] = set()

        if cycle.status == CloseCycleStatus.DRAFT:
            blockers.append(
                ReadinessBlocker(
                    "CYCLE_NOT_STARTED",
                    "lifecycle",
                    "The close cycle has not been started.",
                    "close_cycle",
                    str(cycle_id),
                    "Start the close cycle.",
                )
            )

        unresolved_staged = [
            staged
            for staged in self.s.exec(
                select(StagedTransaction).where(
                    cast(Any, StagedTransaction.date) >= period.start_date,
                    cast(Any, StagedTransaction.date) <= period.end_date,
                    cast(Any, StagedTransaction.status).in_(
                        [WorkflowStatus.INGESTED, WorkflowStatus.VALIDATED, WorkflowStatus.FAILED]
                    ),
                )
            )
            if self._staged_belongs_to_org(staged)
        ]
        if unresolved_staged:
            blockers.append(
                ReadinessBlocker(
                    "STAGED_ITEMS_UNRESOLVED",
                    "workflow",
                    f"{len(unresolved_staged)} staged journal item(s) remain unresolved.",
                    "staged_transaction",
                    str(unresolved_staged[0].id),
                    "Review failed, ingested, and validated staged journals.",
                )
            )
        else:
            completed_system_keys.add("staged_journal_exceptions_resolved")

        trial_balance = LedgerService(self.s, self.organization_id).trial_balance(end_date=period.end_date)
        total_debit = cast(Decimal, trial_balance["total_debit"])
        total_credit = cast(Decimal, trial_balance["total_credit"])
        if total_debit != total_credit:
            blockers.append(
                ReadinessBlocker(
                    "TRIAL_BALANCE_UNBALANCED",
                    "ledger",
                    "The period trial balance is not balanced.",
                    "accounting_period",
                    str(period.id),
                    "Correct the ledger imbalance before close.",
                )
            )
        else:
            completed_system_keys.add("trial_balance_balanced")

        reconciliations = list(
            self.s.exec(
                select(AccountReconciliation).where(
                    AccountReconciliation.organization_id == self.organization_id,
                    AccountReconciliation.cycle_id == cycle_id,
                )
            )
        )
        required_account_ids = {
            int(account_id) for account_id in cycle.policy.get("required_reconciliation_account_ids", [])
        }
        approved_account_ids = {
            item.account_id
            for item in reconciliations
            if item.status == ReconciliationStatus.APPROVED
            and item.ledger_activity_revision == period.ledger_activity_revision
        }
        stale_required_reconciliations = [
            item
            for item in reconciliations
            if item.account_id in required_account_ids
            and item.status == ReconciliationStatus.APPROVED
            and item.ledger_activity_revision != period.ledger_activity_revision
        ]
        missing_required_accounts = sorted(required_account_ids - approved_account_ids)
        if not required_account_ids and not cycle.policy.get("reconciliation_scope_not_applicable", False):
            blockers.append(
                ReadinessBlocker(
                    "RECONCILIATION_SCOPE_UNDEFINED",
                    "reconciliations",
                    "The required reconciliation account scope is empty without an explicit not-applicable policy.",
                    "close_cycle",
                    str(cycle_id),
                    "Define required balance-sheet accounts or record an audited not-applicable policy.",
                )
            )
        elif stale_required_reconciliations:
            blockers.append(
                ReadinessBlocker(
                    "RECONCILIATIONS_STALE",
                    "reconciliations",
                    (
                        f"{len(stale_required_reconciliations)} required reconciliation(s) "
                        "predate current ledger activity."
                    ),
                    "account_reconciliation",
                    str(stale_required_reconciliations[0].id),
                    "Re-prepare and independently approve reconciliations against the current ledger revision.",
                )
            )
        elif missing_required_accounts:
            blockers.append(
                ReadinessBlocker(
                    "RECONCILIATIONS_INCOMPLETE",
                    "reconciliations",
                    f"{len(missing_required_accounts)} required account reconciliation(s) require approval.",
                    "account",
                    str(missing_required_accounts[0]),
                    "Resolve differences and obtain independent approval.",
                )
            )
        else:
            completed_system_keys.add("required_reconciliations_complete")

        variance_run = self.s.exec(
            select(VarianceReviewRun)
            .where(
                VarianceReviewRun.organization_id == self.organization_id,
                VarianceReviewRun.cycle_id == cycle_id,
            )
            .order_by(cast(Any, VarianceReviewRun.id).desc())
        ).first()
        unresolved_variances = (
            list(
                self.s.exec(
                    select(VarianceReview).where(
                        VarianceReview.organization_id == self.organization_id,
                        VarianceReview.cycle_id == cycle_id,
                        VarianceReview.run_id == variance_run.id,
                        cast(Any, VarianceReview.is_material).is_(True),
                        VarianceReview.disposition == VarianceDisposition.UNRESOLVED,
                    )
                )
            )
            if variance_run is not None
            else []
        )
        variance_required = bool(cycle.policy.get("variance_review_required", True))
        if not variance_required:
            completed_system_keys.add("material_variances_reviewed")
        elif variance_run is None:
            blockers.append(
                ReadinessBlocker(
                    "VARIANCE_REVIEW_NOT_RUN",
                    "variance_review",
                    "The required period-scoped variance review has not been run.",
                    "close_cycle",
                    str(cycle_id),
                    "Run the variance review for this accounting period, even when it produces zero rows.",
                )
            )
        elif variance_run is not None and variance_run.ledger_activity_revision != period.ledger_activity_revision:
            blockers.append(
                ReadinessBlocker(
                    "VARIANCE_REVIEW_STALE",
                    "variance_review",
                    "The latest variance review predates current ledger activity.",
                    "variance_review_run",
                    str(variance_run.id),
                    "Run a new period-scoped variance review against the current ledger revision.",
                )
            )
        elif unresolved_variances:
            blockers.append(
                ReadinessBlocker(
                    "MATERIAL_VARIANCES_UNRESOLVED",
                    "variance_review",
                    f"{len(unresolved_variances)} material variance(s) remain unresolved.",
                    "variance_review",
                    str(unresolved_variances[0].id),
                    "Record a disposition and review note for each material variance.",
                )
            )
        else:
            completed_system_keys.add("material_variances_reviewed")

        approvals = list(
            self.s.exec(
                select(JournalApproval).where(
                    JournalApproval.organization_id == self.organization_id,
                    JournalApproval.cycle_id == cycle_id,
                )
            )
        )
        approval_mode = str(cycle.policy.get("journal_approval_mode", "REQUESTED_ONLY"))
        incomplete_approvals = [approval for approval in approvals if approval.status != JournalApprovalStatus.APPROVED]
        if approval_mode == "ALL_PERIOD_TRANSACTIONS":
            period_transaction_ids = {
                transaction_id
                for transaction_id in self.s.exec(
                    select(Transaction.id).where(
                        Transaction.organization_id == self.organization_id,
                        cast(Any, Transaction.date) >= period.start_date,
                        cast(Any, Transaction.date) <= period.end_date,
                    )
                )
                if transaction_id is not None
            }
            approved_transaction_ids = {
                approval.transaction_id
                for approval in approvals
                if approval.transaction_id is not None and approval.status == JournalApprovalStatus.APPROVED
            }
            missing_transaction_ids = sorted(period_transaction_ids - approved_transaction_ids)
            if missing_transaction_ids:
                incomplete_approvals.append(
                    JournalApproval(
                        organization_id=self.organization_id,
                        cycle_id=cycle_id,
                        reference_key=f"transaction:{missing_transaction_ids[0]}",
                        transaction_id=missing_transaction_ids[0],
                        requestor_user_id=self.actor_user_id,
                    )
                )
        if incomplete_approvals:
            blockers.append(
                ReadinessBlocker(
                    "JOURNAL_APPROVALS_INCOMPLETE",
                    "journal_approvals",
                    f"{len(incomplete_approvals)} journal approval request(s) are unresolved.",
                    "journal_approval",
                    str(incomplete_approvals[0].id),
                    "Obtain an independent approval or resolve rejected requests.",
                )
            )
        else:
            completed_system_keys.add("required_journal_approvals_complete")

        evidence = self.s.exec(
            select(CloseEvidence)
            .where(CloseEvidence.organization_id == self.organization_id, CloseEvidence.cycle_id == cycle_id)
            .order_by(cast(Any, CloseEvidence.id).desc())
        ).first()
        evidence_freshness = "MISSING"
        if (
            evidence is not None
            and evidence.source_version == cycle.content_revision
            and evidence.source_ledger_activity_revision == period.ledger_activity_revision
        ):
            evidence_freshness = "CURRENT"
            completed_system_keys.add("close_evidence_generated")
        elif evidence is not None:
            evidence_freshness = "STALE"
        if evidence_freshness != "CURRENT" and cycle.status != CloseCycleStatus.DRAFT:
            evidence_issue = ReadinessBlocker(
                "CLOSE_EVIDENCE_NOT_CURRENT",
                "evidence",
                f"Close evidence is {evidence_freshness.lower()}.",
                "close_cycle",
                str(cycle_id),
                "Generate a current deterministic close evidence bundle.",
            )
            # Evidence is finalized after the ready transition so its source
            # version includes that approval state. Before then it is a warning;
            # once ready it becomes a final-close blocker.
            if cycle.status == CloseCycleStatus.READY_FOR_APPROVAL:
                blockers.append(evidence_issue)
            else:
                warnings.append(evidence_issue)

        tasks = self.list_checklist(cycle_id)
        attestation_pending = [
            task
            for task in tasks
            if task.required
            and task.control_type in {CloseTaskControlType.ATTESTATION, CloseTaskControlType.CUSTOM}
            and task.status != CloseTaskStatus.COMPLETE
        ]
        if attestation_pending:
            blockers.append(
                ReadinessBlocker(
                    "REQUIRED_ATTESTATIONS_INCOMPLETE",
                    "checklist",
                    f"{len(attestation_pending)} required checklist attestation(s) remain incomplete.",
                    "close_checklist_task",
                    str(attestation_pending[0].id),
                    "Complete the required accountant attestations.",
                )
            )
        if cycle.status == CloseCycleStatus.CLOSED:
            completed_system_keys.add("final_close_approved")

        required = [task for task in tasks if task.required]
        effective_task_statuses = {
            task.task_key: (
                CloseTaskStatus.COMPLETE
                if task.task_key in completed_system_keys
                else (
                    CloseTaskStatus.PENDING
                    if task.control_type == CloseTaskControlType.SYSTEM
                    or task.control_type == CloseTaskControlType.ADMIN_APPROVAL
                    else task.status
                )
            )
            for task in tasks
        }
        completed_count = sum(effective_task_statuses[task.task_key] == CloseTaskStatus.COMPLETE for task in required)
        ratio = Decimal(completed_count) / Decimal(len(required)) if required else Decimal("1")
        blockers.sort(key=lambda item: (item.category, item.code, item.source_entity_id or ""))
        warnings.sort(key=lambda item: (item.category, item.code, item.source_entity_id or ""))
        if cycle.status == CloseCycleStatus.CLOSED:
            state = "CLOSED"
        elif cycle.status == CloseCycleStatus.DRAFT:
            state = "NOT_STARTED"
        elif blockers:
            state = "BLOCKED"
        elif cycle.status == CloseCycleStatus.READY_FOR_APPROVAL:
            state = "READY_FOR_APPROVAL"
        else:
            state = "IN_PROGRESS"
        return CloseReadiness(
            cycle_id=cycle_id,
            cycle_status=cycle.status,
            period_status=period.status,
            state=state,
            required_task_count=len(required),
            completed_required_count=completed_count,
            completion_ratio=ratio,
            blocker_count=len(blockers),
            warning_count=len(warnings),
            blockers=tuple(blockers),
            warnings=tuple(warnings),
            evidence_freshness=evidence_freshness,
            version=cycle.version,
            content_revision=cycle.content_revision,
            ledger_activity_revision=period.ledger_activity_revision,
            effective_task_statuses=effective_task_statuses,
            latest_variance_run_id=variance_run.id if variance_run else None,
            latest_variance_run_row_count=variance_run.row_count if variance_run else None,
            latest_variance_run_ledger_activity_revision=(
                variance_run.ledger_activity_revision if variance_run else None
            ),
        )


__all__ = [
    "CloseConflictError",
    "CloseDomainError",
    "CloseNotFoundError",
    "CloseReadiness",
    "CloseService",
    "CloseValidationError",
    "DEFAULT_CHECKLIST",
    "DEFAULT_CLOSE_POLICY",
    "ReadinessBlocker",
    "safe_close_policy",
]
