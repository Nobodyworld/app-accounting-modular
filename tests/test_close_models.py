from apps.api.models import models  # noqa: F401
from sqlalchemy import create_engine, inspect
from sqlmodel import SQLModel


def test_close_constraints_and_tenant_first_indexes() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    try:
        inspector = inspect(engine)
        period_uniques = inspector.get_unique_constraints("accountingperiod")
        assert any(item["name"] == "uq_accounting_period_org_label" for item in period_uniques)
        cycle_uniques = inspector.get_unique_constraints("closecycle")
        assert any(item["name"] == "uq_close_cycle_period" for item in cycle_uniques)
        reconciliation_uniques = inspector.get_unique_constraints("accountreconciliation")
        assert any(item["name"] == "uq_reconciliation_cycle_account" for item in reconciliation_uniques)
        task_uniques = inspector.get_unique_constraints("closechecklisttask")
        assert any(item["name"] == "uq_close_task_cycle_key" for item in task_uniques)
        approval_checks = inspector.get_check_constraints("journalapproval")
        assert any(item["name"] == "ck_journal_approval_one_reference" for item in approval_checks)
        period_indexes = inspector.get_indexes("accountingperiod")
        assert any(item["name"] == "ix_accounting_period_org_dates" for item in period_indexes)
    finally:
        engine.dispose()
