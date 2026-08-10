"""Seed a deterministic multi-user accountant close example into a fresh demo database."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from apps.api.audit import AuditActor, use_actor
from apps.api.db import engine, init_db
from apps.api.models.models import Budget, BudgetLine, JournalApprovalStatus, Membership, Organization, User
from apps.api.security import get_password_hash
from apps.api.services.close_service import CloseService
from apps.api.services.ledger_service import LedgerService
from apps.api.services.reconciliation_service import ReconciliationService
from apps.api.services.workflow_service import WorkflowService
from sqlmodel import Session, select

DEMO_ORGANIZATION = "Accountant Close Demo"
DEMO_LOGIN_VALUE = "close-demo-password"


def seed_close_demo(session: Session) -> dict[str, Any]:
    """Create the controlled blocked-close starting point and return its identifiers."""

    existing = session.exec(select(Organization).where(Organization.name == DEMO_ORGANIZATION)).first()
    if existing is not None:
        raise ValueError("The accountant close demo organization already exists; use a fresh demo database")
    organization = Organization(name=DEMO_ORGANIZATION)
    users = {
        "preparer": User(
            email="close-preparer@example.test",
            password_hash=get_password_hash(DEMO_LOGIN_VALUE),
            name="Alex Preparer",
        ),
        "reviewer": User(
            email="close-reviewer@example.test",
            password_hash=get_password_hash(DEMO_LOGIN_VALUE),
            name="Riley Reviewer",
        ),
        "administrator": User(
            email="close-admin@example.test",
            password_hash=get_password_hash(DEMO_LOGIN_VALUE),
            name="Morgan Administrator",
        ),
    }
    session.add(organization)
    session.add_all(list(users.values()))
    session.commit()
    session.refresh(organization)
    for user in users.values():
        session.refresh(user)
    assert organization.id is not None
    assert all(user.id is not None for user in users.values())
    session.add_all(
        [
            Membership(
                user_id=users["preparer"].id,
                organization_id=organization.id,
                can_manage_ledger=True,
            ),
            Membership(
                user_id=users["reviewer"].id,
                organization_id=organization.id,
                can_manage_ledger=True,
            ),
            Membership(
                user_id=users["administrator"].id,
                organization_id=organization.id,
                can_manage_ledger=True,
                is_admin=True,
            ),
        ]
    )
    session.commit()
    preparer_id = int(users["preparer"].id)
    reviewer_id = int(users["reviewer"].id)
    actor = AuditActor(
        request_id="controlled-close-demo-seed",
        user_id=preparer_id,
        organization_id=organization.id,
        source="demo-seed",
        user_label=users["preparer"].email,
    )
    with use_actor(actor):
        ledger = LedgerService(session, organization.id)
        cash = ledger.create_account("Operating cash", "ASSET", code="1000")
        revenue = ledger.create_account("Service revenue", "REVENUE", code="4000")
        payroll = ledger.create_account("Payroll expense", "EXPENSE", code="6000")
        sale = ledger.post_transaction(
            date(2026, 3, 10),
            "Controlled service revenue",
            [
                {"account_id": cash.id, "debit": 500, "credit": 0},
                {"account_id": revenue.id, "debit": 0, "credit": 500},
            ],
            source="controlled-demo",
            source_reference="demo-sale-1",
        )
        ledger.post_transaction(
            date(2026, 3, 20),
            "Controlled payroll",
            [
                {"account_id": payroll.id, "debit": 120, "credit": 0},
                {"account_id": cash.id, "debit": 0, "credit": 120},
            ],
            source="controlled-demo",
            source_reference="demo-payroll-1",
        )
        budget = Budget(
            organization_id=organization.id,
            name="March 2026 controlled budget",
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        )
        session.add(budget)
        session.commit()
        session.refresh(budget)
        session.add_all(
            [
                BudgetLine(budget_id=budget.id, account_id=revenue.id, period_start=date(2026, 3, 1), amount=-300),
                BudgetLine(budget_id=budget.id, account_id=payroll.id, period_start=date(2026, 3, 1), amount=100),
            ]
        )
        session.commit()
        close = CloseService(session, organization.id, preparer_id)
        period = close.create_period("March 2026", date(2026, 3, 1), date(2026, 3, 31))
        cycle = close.create_cycle(
            period.id,
            "March 2026 Close",
            owner_user_id=preparer_id,
            due_date=date(2026, 4, 5),
        )
        cycle = close.start(cycle.id, cycle.version)
        staged = WorkflowService(session).ingest_transactions(
            [
                {
                    "date": date(2026, 3, 31),
                    "description": "Accrued expense adjustment",
                    "source_reference": "demo-staged-accrual",
                    "postings": [
                        {"account_id": payroll.id, "debit": 25, "credit": 0, "currency": "USD"},
                        {"account_id": cash.id, "debit": 0, "credit": 25, "currency": "USD"},
                    ],
                    "metadata": {"_organization_id": organization.id, "_workflow_source": "controlled-demo"},
                }
            ],
            source=f"controlled-demo::organization:{organization.id}",
            metadata={"_organization_id": organization.id, "_workflow_source": "controlled-demo"},
        )[0]
        controls = ReconciliationService(session, organization.id, preparer_id)
        matched = controls.prepare_reconciliation(
            cycle.id,
            cash.id,
            control_balance=Decimal("380.00"),
            tolerance=Decimal("0.00"),
            notes="Matched to the controlled statement balance.",
        )
        ReconciliationService(session, organization.id, reviewer_id).approve_reconciliation(
            cycle.id, matched.id, version=matched.version
        )
        controls.prepare_reconciliation(
            cycle.id,
            payroll.id,
            control_balance=Decimal("140.00"),
            tolerance=Decimal("0.00"),
            notes="Twenty-dollar payroll cutoff difference remains under review.",
        )
        controls.materialize_variances(
            cycle.id,
            budget_id=budget.id,
            horizon=30,
            absolute_threshold=Decimal("100.00"),
            percentage_threshold=Decimal("0.10"),
        )
        approval = controls.request_approval(
            cycle.id,
            transaction_id=sale.id,
            reason="Independent close approval for the posted revenue journal.",
        )
        ReconciliationService(session, organization.id, reviewer_id).decide_approval(
            cycle.id,
            approval.id,
            version=approval.version,
            decision=JournalApprovalStatus.APPROVED,
            reason="Journal support reviewed.",
        )
    return {
        "organization_id": organization.id,
        "period_id": period.id,
        "cycle_id": cycle.id,
        "budget_id": budget.id,
        "staged_transaction_id": staged.id,
        "cash_account_id": cash.id,
        "revenue_account_id": revenue.id,
        "payroll_account_id": payroll.id,
        "users": {role: user.email for role, user in users.items()},
        "password": DEMO_LOGIN_VALUE,
    }


def main() -> int:
    init_db()
    with Session(engine, expire_on_commit=False) as session:
        payload = seed_close_demo(session)
    print("Controlled accountant close demo created:")
    for key, value in payload.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
