"""Synthetic accountant-close rehearsal; never a production database runner."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BALANCES = {"1000": "355.00", "4000": "-500.00", "6000": "145.00"}
MAX_BUNDLE_BYTES = 4 * 1024 * 1024


class PilotError(ValueError):
    """A bounded diagnostic code, without personal paths or input values."""


def _check(condition: bool, code: str) -> None:
    if not condition:
        raise PilotError(code)


def _expect_error(operation: Any, error_type: Any, code: str | None = None) -> None:
    try:
        operation()
    except error_type as exc:
        if code is not None:
            _check(exc.code == code, "PILOT_WRONG_REJECTION")
    else:
        raise PilotError("PILOT_EXPECTED_REJECTION_MISSING")


def run_rehearsal() -> tuple[dict[str, Any], bytes]:
    """Exercise the real seeded services in an owned, in-memory database.

    This is service-layer acceptance, not authenticated HTTP or browser testing.
    The command-line entry point supplies process and network isolation before
    importing the application. Tests may call this in their isolated test process.
    """
    from apps.api.audit import AuditActor, use_actor
    from apps.api.models.models import (
        AuditLog,
        CloseTaskControlType,
        JournalEntry,
        Transaction,
        User,
        VarianceDisposition,
        WorkflowStatus,
    )
    from apps.api.services.close_evidence_service import CloseEvidenceService
    from apps.api.services.close_service import CloseConflictError, CloseEvidenceNotCurrentError, CloseService
    from apps.api.services.ledger_service import LedgerService
    from apps.api.services.period_lock import PeriodPostingError
    from apps.api.services.reconciliation_service import ReconciliationService
    from apps.api.services.workflow_service import WorkflowService
    from sqlmodel import Session, SQLModel, create_engine, select

    from scripts.seed_close_demo import seed_close_demo

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    trace: list[dict[str, Any]] = []
    checks: list[str] = []
    try:
        with Session(engine, expire_on_commit=False) as session:
            seeded = seed_close_demo(session)
            org = seeded["organization_id"]
            cycle_id = seeded["cycle_id"]
            users = {
                role: session.exec(select(User).where(User.email == email)).one()
                for role, email in seeded["users"].items()
            }
            preparer = CloseService(session, org, users["preparer"].id)
            administrator = CloseService(session, org, users["administrator"].id)
            controls = ReconciliationService(session, org, users["preparer"].id)
            reviewer = ReconciliationService(session, org, users["reviewer"].id)
            evidence = CloseEvidenceService(session, org, users["preparer"].id)
            ledger = LedgerService(session, org)

            def actor(role: str) -> Any:
                return use_actor(
                    AuditActor(
                        request_id=f"controlled-close-pilot-{role}",
                        user_id=users[role].id,
                        organization_id=org,
                        source="close-pilot",
                        user_label=users[role].email,
                    )
                )

            def observe(stage: str) -> Any:
                current = preparer.readiness(cycle_id)
                trace.append(
                    {
                        "stage": stage,
                        "state": current.state,
                        "blocker_codes": sorted({item.code for item in current.blockers}),
                        "evidence_freshness": current.evidence_freshness,
                        "ledger_activity_revision": current.ledger_activity_revision,
                    }
                )
                return current

            def counts() -> tuple[int, int, int]:
                return tuple(len(session.exec(select(model)).all()) for model in (Transaction, JournalEntry, AuditLog))

            def post_probe() -> Any:
                return ledger.post_transaction(
                    date(2026, 3, 31),
                    "Controlled posting-lock probe",
                    [
                        {"account_id": seeded["cash_account_id"], "debit": 1, "credit": 0},
                        {"account_id": seeded["revenue_account_id"], "debit": 0, "credit": 1},
                    ],
                )

            initial = observe("seeded")
            _check(initial.blocker_count > 0, "PILOT_INITIAL_BLOCKERS_MISSING")
            cycle = preparer.require_cycle(cycle_id)
            _check(cycle.policy["journal_approval_mode"] == "REQUESTED_ONLY", "PILOT_POLICY_CHANGED")
            _check(cycle.policy["variance_review_required"] is True, "PILOT_POLICY_CHANGED")
            with actor("preparer"):
                _expect_error(lambda: preparer.mark_ready(cycle_id, cycle.version), CloseConflictError)
                draft = evidence.build_bundle(cycle_id)
                evidence.record_generation(cycle_id, draft)
                result = WorkflowService(session).process_transactions([seeded["staged_transaction_id"]])
            _check(len(result) == 1 and result[0].status == WorkflowStatus.POSTED, "PILOT_STAGED_POST_FAILED")
            _expect_error(lambda: evidence.require_current_recorded_bundle(cycle_id), CloseEvidenceNotCurrentError)
            posted = observe("adjustment_posted")
            _check(posted.ledger_activity_revision > initial.ledger_activity_revision, "PILOT_REVISION_NOT_ADVANCED")
            checks.extend(["seed_starts_blocked", "staged_adjustment_posts", "posting_stales_recorded_evidence"])

            account_ids = {
                "1000": seeded["cash_account_id"],
                "4000": seeded["revenue_account_id"],
                "6000": seeded["payroll_account_id"],
            }
            balances = {code: controls.ledger_ending_balance(cycle_id, key) for code, key in account_ids.items()}
            _check(
                balances == {code: Decimal(value) for code, value in EXPECTED_BALANCES.items()},
                "PILOT_BALANCE_MISMATCH",
            )
            _check(sum(balances.values(), Decimal("0")) == 0, "PILOT_UNBALANCED")
            checks.append("independent_expected_balances")

            stale = controls.list_reconciliations(cycle_id)
            _check(len(stale) == 2, "PILOT_RECONCILIATION_SCOPE")
            _check(
                all(row.ledger_activity_revision < posted.ledger_activity_revision for row in stale),
                "PILOT_RECONCILIATION_STALENESS_MISSING",
            )
            for row in stale:
                code = next(code for code, key in account_ids.items() if key == row.account_id)
                with actor("preparer"):
                    refreshed = controls.prepare_reconciliation(
                        cycle_id,
                        row.account_id,
                        control_balance=Decimal(EXPECTED_BALANCES[code]),
                        tolerance=Decimal("0.00"),
                        version=row.version,
                        notes="Controlled post-adjustment support independently checked.",
                    )
                    before = counts()
                    _expect_error(
                        lambda item=refreshed: controls.approve_reconciliation(cycle_id, item.id, version=item.version),
                        CloseConflictError,
                    )
                    _check(counts() == before, "PILOT_SELF_APPROVAL_MUTATED")
                with actor("reviewer"):
                    reviewer.approve_reconciliation(cycle_id, refreshed.id, version=refreshed.version)
            checks.extend(["both_stale_reconciliations_refreshed", "independent_approval_enforced"])

            with actor("preparer"):
                variances = controls.materialize_variances(
                    cycle_id,
                    budget_id=seeded["budget_id"],
                    horizon=30,
                    absolute_threshold=Decimal("100.00"),
                    percentage_threshold=Decimal("0.10"),
                    refresh=True,
                )
            _check(len(variances) == 2 and all(row.is_material for row in variances), "PILOT_MATERIALITY_MISMATCH")
            variance_summary = []
            for row in variances:
                with actor("reviewer"):
                    reviewer.update_variance(
                        cycle_id,
                        row.id,
                        version=row.version,
                        disposition=VarianceDisposition.EXPLAINED,
                        note="Synthetic actual activity differs from the controlled budget; support reviewed.",
                    )
                variance_summary.append(
                    {
                        "account_code": next(code for code, key in account_ids.items() if key == row.account_id),
                        "budget": str(row.budget_amount),
                        "actual": str(row.actual_amount),
                        "variance": str(row.variance_amount),
                        "material": bool(row.is_material),
                        "disposition": row.disposition.value,
                    }
                )
            with actor("preparer"):
                attestation = next(
                    task
                    for task in preparer.list_checklist(cycle_id)
                    if task.control_type == CloseTaskControlType.ATTESTATION
                )
                preparer.update_manual_task(
                    cycle_id,
                    attestation.id,
                    version=attestation.version,
                    complete=True,
                    notes="Synthetic local source and regenerated report reviewed; no live provider used.",
                )
                reconciled = observe("controls_completed")
                _check(reconciled.blocker_count == 0, "PILOT_READINESS_BLOCKED")
                cycle = preparer.require_cycle(cycle_id)
                cycle = preparer.mark_ready(cycle_id, cycle.version)
                before = counts()
                _expect_error(post_probe, PeriodPostingError, "ACCOUNTING_PERIOD_CLOSE_READY")
                _check(counts() == before, "PILOT_READY_POST_MUTATED")
                observe("ready_for_approval")
                ready_bundle = evidence.build_bundle(cycle_id)
                evidence.record_generation(cycle_id, ready_bundle)
            checks.extend(["current_material_variances_reviewed", "ready_freezes_posting_without_partial_writes"])

            with actor("administrator"):
                cycle = administrator.require_cycle(cycle_id)
                cycle = administrator.close(cycle_id, cycle.version)
                closed = observe("closed")
                _check(closed.state == "CLOSED" and closed.evidence_freshness == "CURRENT", "PILOT_FINAL_NOT_CURRENT")
                final = evidence.require_current_recorded_bundle(cycle_id)
                repeated = evidence.require_current_recorded_bundle(cycle_id)
                _check(final.content == repeated.content, "PILOT_RECORDED_BYTES_CHANGED")
                _check(0 < len(final.content) <= MAX_BUNDLE_BYTES, "PILOT_BUNDLE_SIZE")
                with ZipFile(BytesIO(final.content)) as archive:
                    _check(len(archive.namelist()) == len(final.files) + 1, "PILOT_ARCHIVE_INVENTORY")
                    for item in final.files:
                        content = archive.read(item.name)
                        _check(len(content) == item.byte_length, "PILOT_FILE_LENGTH")
                        _check(hashlib.sha256(content).hexdigest() == item.sha256, "PILOT_FILE_DIGEST")
                    _check(json.loads(archive.read("readiness.json"))["state"] == "CLOSED", "PILOT_BUNDLE_NOT_FINAL")
                before = counts()
                _expect_error(post_probe, PeriodPostingError, "ACCOUNTING_PERIOD_CLOSED")
                _check(counts() == before, "PILOT_CLOSED_POST_MUTATED")
                checks.extend(
                    [
                        "closed_has_current_recorded_evidence",
                        "recorded_bytes_and_file_digests",
                        "closed_freezes_posting",
                    ]
                )
                cycle = administrator.require_cycle(cycle_id)
                administrator.reopen(cycle_id, cycle.version, "Controlled rehearsal of explicit post-close review")
                _expect_error(lambda: evidence.require_current_recorded_bundle(cycle_id), CloseEvidenceNotCurrentError)
                reopened = observe("reopened")
                _check(reopened.evidence_freshness == "STALE", "PILOT_REOPEN_NOT_STALE")
                post_probe()
            checks.append("explicit_reopen_stales_evidence_and_allows_posting")
            return {
                "schema_version": "accountant-close-pilot-v1",
                "classification": "SYNTHETIC_REHEARSAL_NOT_PRODUCTION_ACCEPTANCE",
                "acceptance_layer": "services",
                "human_pilot": "NOT_RUN",
                "browser_acceptance": "NOT_RUN",
                "status": "PASS",
                "scenario": "March 2026 controlled accountant close",
                "journal_approval_mode": "REQUESTED_ONLY",
                "final_close_balances_debit_minus_credit_usd": EXPECTED_BALANCES.copy(),
                "variances": sorted(variance_summary, key=lambda item: item["account_code"]),
                "checks": checks,
                "trace": trace,
                "closed_evidence": {
                    "filename": "close-final.zip",
                    "sha256": hashlib.sha256(final.content).hexdigest(),
                    "manifest_sha256": final.manifest_sha256,
                    "byte_length": len(final.content),
                    "source_status": final.source_status.value,
                    "current_at_capture": True,
                    "current_after_reopen": False,
                },
            }, final.content
    finally:
        engine.dispose()


def _deny_network() -> None:
    def denied(*args: Any, **kwargs: Any) -> Any:
        raise PilotError("PILOT_NETWORK_DENIED")

    socket.create_connection = denied
    socket.socket.connect = denied  # type: ignore[method-assign]
    socket.socket.connect_ex = denied  # type: ignore[method-assign]
    socket.getaddrinfo = denied


def _worker() -> int:
    _deny_network()
    try:
        report, bundle = run_rehearsal()
        report["network_policy"] = "python_socket_connections_denied"
        report["source_head"] = os.environ.get("CLOSE_PILOT_SOURCE_HEAD", "UNKNOWN")
        report["source_tree"] = os.environ.get("CLOSE_PILOT_SOURCE_TREE", "UNKNOWN")
        report["source_clean"] = os.environ.get("CLOSE_PILOT_SOURCE_CLEAN") == "true"
        report["python_version"] = sys.version.split()[0]
        payload = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
        _check(len(payload) <= 64 * 1024, "PILOT_REPORT_SIZE")
        with Path("close-final.zip").open("xb") as output:
            output.write(bundle)
        with Path("close-pilot.json").open("xb") as output:
            output.write(payload)
        return 0
    except Exception:
        print("PILOT_EXECUTION_FAILED", file=sys.stderr)
        return 1


def _git_value(*args: str) -> str:
    result = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=15, check=True)
    return result.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="A new directory under an existing parent; never overwritten.")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        return _worker()
    if args.output is None:
        parser.error("--output is required")
    try:
        target = args.output.absolute()
        _check(".." not in target.parts, "PILOT_OUTPUT_INVALID")
        _check(not target.exists() and not target.is_symlink(), "PILOT_OUTPUT_EXISTS")
        _check(target.parent.is_dir(), "PILOT_OUTPUT_PARENT_MISSING")
        for parent in target.parents:
            _check(
                not parent.is_symlink() and not getattr(parent, "is_junction", lambda: False)(),
                "PILOT_OUTPUT_LINK_REJECTED",
            )
        head = _git_value("rev-parse", "HEAD")
        tree = _git_value("rev-parse", "HEAD^{tree}")
        clean = not _git_value("status", "--porcelain=v1", "--untracked-files=all")
        _check(clean, "PILOT_SOURCE_NOT_CLEAN")
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE", "LANG", "LC_ALL"}
        }
        environment.update(
            {
                "PYTHONPATH": os.pathsep.join(
                    str(path) for path in (ROOT / "src", ROOT / "packages/provider-sdk/src", ROOT)
                ),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
                "DATABASE_URL": "sqlite://",
                "MODACCT_DATABASE_URL": "sqlite://",
                "MODACCT_ENV_FILE": "",
                "MODACCT_TRACING_EXPORTER": "disabled",
                "MODACCT_LOG_DESTINATION": "null",
                "CLOSE_PILOT_SOURCE_HEAD": head,
                "CLOSE_PILOT_SOURCE_TREE": tree,
                "CLOSE_PILOT_SOURCE_CLEAN": "true",
            }
        )
        target.mkdir()
        result = subprocess.run(
            [sys.executable, "-m", "scripts.accountant_close_pilot", "--worker"],
            cwd=target,
            env=environment,
            capture_output=True,
            timeout=180,
            check=False,
        )
        _check(result.returncode == 0, "PILOT_EXECUTION_FAILED")
        print("PASS: close-pilot.json and close-final.zip created; human/browser pilot NOT RUN.")
        return 0
    except PilotError as exc:
        print(str(exc), file=sys.stderr)
    except (OSError, subprocess.SubprocessError):
        print("PILOT_SETUP_FAILED", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
