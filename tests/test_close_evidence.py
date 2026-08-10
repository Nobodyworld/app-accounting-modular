from __future__ import annotations

from dataclasses import replace
from datetime import date
from io import BytesIO
from zipfile import ZipFile

import pytest
from apps.api.models.models import AuditLog
from apps.api.services import close_evidence_service as evidence_module
from apps.api.services.close_evidence_service import CloseEvidenceService
from apps.api.services.close_service import (
    CloseEvidenceNotCurrentError,
    CloseService,
    CloseValidationError,
)
from apps.api.services.ledger_service import LedgerService
from apps.api.services.reconciliation_service import ReconciliationService
from sqlmodel import select

from tests._close_helpers import close_session


def test_evidence_bundle_is_byte_deterministic_and_manifested() -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id
        close = CloseService(session, actors.organization.id, actors.preparer.id)
        period = close.create_period("November 2026", date(2026, 11, 1), date(2026, 11, 30))
        cycle = close.create_cycle(period.id, "November close")
        evidence = CloseEvidenceService(session, actors.organization.id, actors.preparer.id)
        first = evidence.build_bundle(cycle.id)
        second = evidence.build_bundle(cycle.id)
        assert first.content == second.content
        assert first.manifest_sha256 == second.manifest_sha256
        with ZipFile(BytesIO(first.content)) as archive:
            assert archive.namelist()[0] == "manifest.json"
            assert archive.read("readiness.json").endswith(b"\n")
            assert b"Early Beta / Portfolio Preview" in archive.read("provenance.json")
            assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist())


def test_recorded_evidence_download_remains_deterministic() -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id
        close = CloseService(session, actors.organization.id, actors.preparer.id)
        period = close.create_period("December 2026", date(2026, 12, 1), date(2026, 12, 31))
        cycle = close.create_cycle(period.id, "December close")
        evidence = CloseEvidenceService(session, actors.organization.id, actors.preparer.id)
        generated = evidence.build_bundle(cycle.id)
        record = evidence.record_generation(cycle.id, generated)
        rebuilt = evidence.build_bundle(cycle.id)
        with (
            ZipFile(BytesIO(generated.content)) as generated_archive,
            ZipFile(BytesIO(rebuilt.content)) as rebuilt_archive,
        ):
            differing_files = [
                name
                for name in generated_archive.namelist()
                if generated_archive.read(name) != rebuilt_archive.read(name)
            ]
        assert not differing_files, differing_files
        downloaded = evidence.require_current_recorded_bundle(cycle.id)
        repeated = evidence.require_current_recorded_bundle(cycle.id)
        assert generated.content == downloaded.content
        assert downloaded.content == repeated.content
        assert record.manifest_sha256 == generated.manifest_sha256 == downloaded.manifest_sha256
        audit = session.exec(
            select(AuditLog)
            .where(AuditLog.entity_name == "CloseEvidence", AuditLog.entity_id == str(record.id))
            .order_by(AuditLog.id.desc())
        ).first()
        assert audit is not None and audit.after_state is not None
        assert audit.context is not None and audit.context["event"] == "close_evidence_generated"
        assert audit.after_state["manifest_sha256"] == downloaded.manifest_sha256
        assert evidence.preview(cycle.id)["freshness"] == "CURRENT"


def test_evidence_serialization_and_resource_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    class ValueObject:
        value = "CONTROLLED"

    assert evidence_module._json_default(ValueObject()) == "CONTROLLED"
    with pytest.raises(TypeError, match="Unsupported JSON value"):
        evidence_module._json_default(object())

    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id
        close = CloseService(session, actors.organization.id, actors.preparer.id)
        period = close.create_period("January 2027", date(2027, 1, 1), date(2027, 1, 31))
        cycle = close.create_cycle(period.id, "January close")
        evidence = CloseEvidenceService(session, actors.organization.id, actors.preparer.id)
        bundle = evidence.build_bundle(cycle.id)
        with pytest.raises(CloseValidationError, match="source version"):
            evidence.record_generation(cycle.id, replace(bundle, source_version=bundle.source_version + 1))
        monkeypatch.setattr(evidence_module, "MAX_EVIDENCE_ROWS", -1)
        with pytest.raises(CloseValidationError, match="maximum row count"):
            evidence.build_bundle(cycle.id)
        monkeypatch.setattr(evidence_module, "MAX_EVIDENCE_ROWS", 10_000)
        monkeypatch.setattr(evidence_module, "MAX_EVIDENCE_ARCHIVE_BYTES", 1)
        with pytest.raises(CloseValidationError, match="maximum archive size"):
            evidence.build_bundle(cycle.id)


def test_recorded_download_stales_after_ledger_activity() -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id
        close = CloseService(session, actors.organization.id, actors.preparer.id)
        period = close.create_period("February 2027", date(2027, 2, 1), date(2027, 2, 28))
        cycle = close.create_cycle(period.id, "February close")
        evidence = CloseEvidenceService(session, actors.organization.id, actors.preparer.id)
        evidence.record_generation(cycle.id, evidence.build_bundle(cycle.id))
        assert evidence.require_current_recorded_bundle(cycle.id)

        ledger = LedgerService(session, actors.organization.id)
        cash = ledger.create_account("Cash", "ASSET", code="1000")
        revenue = ledger.create_account("Revenue", "REVENUE", code="4000")
        ledger.post_transaction(
            date(2027, 2, 10),
            "Late activity",
            [
                {"account_id": cash.id, "debit": 10, "credit": 0},
                {"account_id": revenue.id, "debit": 0, "credit": 10},
            ],
        )

        with pytest.raises(CloseEvidenceNotCurrentError):
            evidence.require_current_recorded_bundle(cycle.id)


def test_evidence_account_lookup_is_limited_to_sorted_references(monkeypatch: pytest.MonkeyPatch) -> None:
    with close_session() as (session, actors):
        assert actors.organization.id and actors.preparer.id
        ledger = LedgerService(session, actors.organization.id)
        accounts = [ledger.create_account(f"Account {index}", "ASSET", code=f"1{index:03d}") for index in range(8)]
        close = CloseService(session, actors.organization.id, actors.preparer.id)
        period = close.create_period("March 2027", date(2027, 3, 1), date(2027, 3, 31))
        cycle = close.create_cycle(period.id, "March close")
        cycle = close.start(cycle.id, cycle.version)
        reconciliation = ReconciliationService(session, actors.organization.id, actors.preparer.id)
        for account in (accounts[5], accounts[2]):
            reconciliation.prepare_reconciliation(
                cycle.id,
                account_id=account.id,
                control_balance=0,
                tolerance=0,
            )

        evidence = CloseEvidenceService(session, actors.organization.id, actors.preparer.id)
        original_bounded = evidence._bounded
        account_lookup_params: list[list[int]] = []

        def inspect_bounded(statement, used):
            sql = str(statement)
            if "FROM account \n" in sql and "account.id IN" in sql:
                values = [value for value in statement.compile().params.values() if isinstance(value, list)]
                account_lookup_params.extend(values)
            return original_bounded(statement, used)

        monkeypatch.setattr(evidence, "_bounded", inspect_bounded)
        evidence.build_bundle(cycle.id)
        expected = sorted([accounts[2].id, accounts[5].id])
        assert account_lookup_params == [expected]
        assert all(account.id not in account_lookup_params[0] for account in accounts if account.id not in expected)
