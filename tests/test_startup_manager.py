"""Tests for the structured API startup orchestration helpers."""

from __future__ import annotations

import logging

import pytest
from apps.api.startup import StartupFailure, StartupManager, StartupStep


def _make_clock(step: float = 0.1):
    """Return a deterministic monotonic clock for tests."""

    current = -step

    def _clock() -> float:
        nonlocal current
        current += step
        return current

    return _clock


def test_startup_manager_runs_steps_and_records_summary(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    manager = StartupManager(clock=_make_clock())
    context: dict[str, object] = {}
    execution_order: list[str] = []

    def first_step(ctx: dict[str, object]) -> None:
        execution_order.append("first")
        ctx["value"] = 1

    def second_step(ctx: dict[str, object]) -> None:
        execution_order.append("second")
        ctx["value"] = int(ctx["value"]) + 1

    records = manager.run(
        (
            StartupStep(name="first", action=first_step),
            StartupStep(name="second", action=second_step),
        ),
        context=context,
    )

    assert execution_order == ["first", "second"]
    assert context["value"] == 2
    assert [record.status for record in records] == ["success", "success"]
    assert any("Startup sequence completed" in message for message in caplog.messages)


def test_startup_manager_handles_non_fatal_failures(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    manager = StartupManager(clock=_make_clock())
    context: dict[str, object] = {}

    def failing_step(_: dict[str, object]) -> None:
        raise RuntimeError("boom")

    def recovery_step(ctx: dict[str, object]) -> None:
        ctx["recovered"] = True

    records = manager.run(
        (
            StartupStep(name="optional", action=failing_step, fatal=False),
            StartupStep(name="recovery", action=recovery_step),
        ),
        context=context,
    )

    assert context["recovered"] is True
    assert [record.status for record in records] == ["error", "success"]
    error_logs = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert error_logs, "expected error log for non-fatal failure"


def test_startup_manager_raises_on_fatal_failure() -> None:
    manager = StartupManager(clock=_make_clock())

    def fatal(_: dict[str, object]) -> None:
        raise RuntimeError("nope")

    with pytest.raises(StartupFailure) as excinfo:
        manager.run((StartupStep(name="fatal", action=fatal),), context={})

    assert excinfo.value.step_name == "fatal"
    assert excinfo.value.records, "expected failure to expose executed records"
    assert excinfo.value.records[0].status == "error"


def test_startup_manager_logs_abort_summary(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    manager = StartupManager(clock=_make_clock())

    def fatal(_: dict[str, object]) -> None:
        raise RuntimeError("boom")

    with pytest.raises(StartupFailure):
        manager.run((StartupStep(name="fatal", action=fatal),), context={})

    abort_logs = [record for record in caplog.records if record.message == "Startup sequence aborted"]
    assert abort_logs, "expected abort summary log"
    summary = abort_logs[0].startup_steps
    assert summary[0]["status"] == "error"
    assert summary[0]["fatal"] is True
    assert abort_logs[0].startup_error["step"] == "fatal"


def test_startup_manager_records_skipped_steps(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    manager = StartupManager(clock=_make_clock())
    context: dict[str, object] = {}

    records = manager.run(
        (
            StartupStep(name="optional", action=lambda _: None, enabled=False),
            StartupStep(name="required", action=lambda ctx: ctx.setdefault("ran", True)),
        ),
        context=context,
    )

    assert context["ran"] is True
    assert [record.status for record in records] == ["skipped", "success"]
    skip_logs = [record for record in caplog.records if record.message == "Startup step skipped"]
    assert skip_logs, "expected skip log entry"
    assert skip_logs[0].startup_step["status"] == "skipped"
