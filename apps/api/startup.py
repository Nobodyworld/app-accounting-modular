"""Structured application startup orchestration helpers.

This module contains a small framework for executing startup steps with
structured logging and duration tracking.  The goal is to provide a single
place where the API initialisation sequence can be described, monitored, and
tested without spreading error-handling concerns across the application
factory.  Each step receives a shared, mutable context dictionary so steps can
communicate lightweight results (for example, extension manifests) without
depending on global variables.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, MutableMapping, Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Literal

__all__ = [
    "StartupContext",
    "StartupFailure",
    "StartupManager",
    "StartupRecord",
    "StartupStep",
]


StartupContext = MutableMapping[str, Any]


class StartupFailure(RuntimeError):
    """Raised when a fatal startup step fails."""

    def __init__(self, step_name: str, error: BaseException):
        self.step_name = step_name
        self.error = error
        message = f"Startup step '{step_name}' failed: {error!s}"
        super().__init__(message)


@dataclass(slots=True)
class StartupStep:
    """Definition of a single startup step.

    Attributes
    ----------
    name:
        Human-readable identifier used in logs and error messages.
    action:
        Callable invoked to perform the step.  The callable receives a mutable
        startup context dictionary that is shared across all steps.
    fatal:
        When ``True`` (the default) a raised exception aborts the startup
        sequence and surfaces a :class:`StartupFailure`.  Non-fatal steps log
        the exception and execution proceeds.
    enabled:
        When ``False`` the step is skipped and a ``"skipped"`` record is
        emitted.
    """

    name: str
    action: Callable[[StartupContext], None]
    fatal: bool = True
    enabled: bool = True


@dataclass(slots=True, frozen=True)
class StartupRecord:
    """Execution metadata for a startup step."""

    name: str
    status: Literal["success", "error", "skipped"]
    duration: float
    fatal: bool
    error: BaseException | None = None

    def as_dict(self) -> dict[str, Any]:
        """Represent the record as a JSON-serialisable dictionary."""

        payload: dict[str, Any] = {
            "name": self.name,
            "status": self.status,
            "duration": round(self.duration, 6),
            "fatal": self.fatal,
        }
        if self.error is not None:
            payload["error"] = type(self.error).__name__
            payload["error_message"] = str(self.error)
        return payload


class StartupManager:
    """Execute startup steps with structured logging and error handling."""

    def __init__(
        self,
        *,
        logger: logging.Logger | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._logger = logger or logging.getLogger(__name__)
        self._clock = clock or perf_counter

    def run(
        self,
        steps: Sequence[StartupStep],
        *,
        context: StartupContext | None = None,
    ) -> tuple[StartupRecord, ...]:
        """Execute ``steps`` sequentially and return execution metadata."""

        ctx: StartupContext = context if context is not None else {}
        records: list[StartupRecord] = []
        for step in steps:
            if not step.enabled:
                record = StartupRecord(
                    name=step.name,
                    status="skipped",
                    duration=0.0,
                    fatal=step.fatal,
                )
                self._logger.info(
                    "Startup step skipped",
                    extra={"startup_step": record.as_dict()},
                )
                records.append(record)
                continue

            start = self._clock()
            try:
                step.action(ctx)
            except Exception as exc:
                duration = self._clock() - start
                record = StartupRecord(
                    name=step.name,
                    status="error",
                    duration=duration,
                    fatal=step.fatal,
                    error=exc,
                )
                self._logger.exception(
                    "Startup step failed",
                    extra={"startup_step": record.as_dict()},
                )
                records.append(record)
                if step.fatal:
                    summary = [startup_record.as_dict() for startup_record in records]
                    self._logger.error(
                        "Startup sequence aborted",
                        extra={"startup_steps": summary},
                    )
                    raise StartupFailure(step.name, exc) from exc
                continue

            duration = self._clock() - start
            record = StartupRecord(
                name=step.name,
                status="success",
                duration=duration,
                fatal=step.fatal,
            )
            self._logger.info(
                "Startup step completed",
                extra={"startup_step": record.as_dict()},
            )
            records.append(record)

        summary = [record.as_dict() for record in records]
        self._logger.info("Startup sequence completed", extra={"startup_steps": summary})
        return tuple(records)
