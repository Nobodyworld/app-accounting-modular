from __future__ import annotations

from dataclasses import replace
from datetime import date
from io import BytesIO
from zipfile import ZipFile

import pytest
from apps.api.services import close_evidence_service as evidence_module
from apps.api.services.close_evidence_service import CloseEvidenceService
from apps.api.services.close_service import CloseService, CloseValidationError

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
        evidence.record_generation(cycle.id, generated)
        downloaded = evidence.build_bundle(cycle.id)
        repeated = evidence.build_bundle(cycle.id)
        assert downloaded.content == repeated.content
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
