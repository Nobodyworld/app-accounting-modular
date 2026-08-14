"""Deterministic structural conformance checks for provider packages."""

from __future__ import annotations

import importlib
import inspect
import json
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Literal, get_type_hints

from .contracts import CAPABILITY_PARAMETERS, PROVIDER_SDK_VERSION, ProviderManifest

CheckStatus = Literal["pass", "fail", "warning"]


@dataclass(frozen=True, slots=True)
class ConformanceCheck:
    """One deterministic conformance result."""

    code: str
    status: CheckStatus
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "status": self.status, "message": self.message}


@dataclass(frozen=True, slots=True)
class ProviderConformanceReport:
    """Serializable structural conformance evidence."""

    module: str
    checks: tuple[ConformanceCheck, ...]
    manifest: ProviderManifest | None = None

    @property
    def passed(self) -> bool:
        return all(check.status != "fail" for check in self.checks)

    @property
    def failure_codes(self) -> tuple[str, ...]:
        return tuple(check.code for check in self.checks if check.status == "fail")

    def to_dict(self) -> dict[str, object]:
        return {
            "module": self.module,
            "passed": self.passed,
            "manifest": self.manifest.to_dict() if self.manifest is not None else None,
            "checks": [check.to_dict() for check in self.checks],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


class ProviderConformanceError(ValueError):
    """Raised when a provider package fails a required conformance check."""

    def __init__(self, report: ProviderConformanceReport):
        self.report = report
        codes = ", ".join(report.failure_codes) or "unknown"
        super().__init__(f"Provider conformance failed: {codes}")


@dataclass(frozen=True, slots=True)
class ConformingProvider:
    """A provider instance loaded through the conformance boundary."""

    instance: Any
    manifest: ProviderManifest
    report: ProviderConformanceReport


@dataclass(slots=True)
class _Evaluation:
    module: ModuleType | None
    manifest: ProviderManifest | None
    instance: Any | None
    checks: list[ConformanceCheck]


def _check(code: str, status: CheckStatus, message: str) -> ConformanceCheck:
    return ConformanceCheck(code=code, status=status, message=message)


def _safe_failure(action: str, exc: BaseException) -> str:
    return f"{action} failed ({type(exc).__name__})"


def _module_name(module_or_name: str | ModuleType) -> str:
    return module_or_name if isinstance(module_or_name, str) else module_or_name.__name__


def _import_module(module_or_name: str | ModuleType, evaluation: _Evaluation) -> bool:
    if isinstance(module_or_name, ModuleType):
        evaluation.module = module_or_name
        evaluation.checks.append(_check("module.import", "pass", "module supplied"))
        return True
    try:
        evaluation.module = importlib.import_module(module_or_name)
    except Exception as exc:
        evaluation.checks.append(_check("module.import", "fail", _safe_failure("module import", exc)))
        return False
    evaluation.checks.append(_check("module.import", "pass", "module imported"))
    return True


def _parse_api_major(api_version: str) -> int | None:
    first = api_version.split(".", 1)[0].strip()
    return int(first) if first.isdigit() else None


def _validate_manifest(
    evaluation: _Evaluation,
    *,
    expected_key: str | None,
    expected_capabilities: tuple[str, ...] | None,
    api_version: str,
) -> bool:
    assert evaluation.module is not None
    manifest = getattr(evaluation.module, "PROVIDER_MANIFEST", None)
    if not isinstance(manifest, ProviderManifest):
        evaluation.checks.append(
            _check("manifest.present", "fail", "PROVIDER_MANIFEST must be a ProviderManifest")
        )
        return False

    evaluation.manifest = manifest
    evaluation.checks.append(_check("manifest.present", "pass", "provider manifest is valid"))

    if manifest.sdk_version == PROVIDER_SDK_VERSION:
        evaluation.checks.append(_check("manifest.sdk", "pass", "provider SDK version is compatible"))
    else:
        evaluation.checks.append(
            _check(
                "manifest.sdk",
                "fail",
                f"provider SDK {manifest.sdk_version} does not match {PROVIDER_SDK_VERSION}",
            )
        )

    api_major = _parse_api_major(api_version)
    if api_major is None:
        evaluation.checks.append(_check("manifest.api", "fail", "application API version is invalid"))
    elif manifest.api_major != api_major:
        evaluation.checks.append(
            _check(
                "manifest.api",
                "fail",
                f"provider API major {manifest.api_major} does not match application major {api_major}",
            )
        )
    else:
        evaluation.checks.append(_check("manifest.api", "pass", "provider API major is compatible"))

    if expected_key is None or manifest.key == expected_key:
        evaluation.checks.append(_check("manifest.key", "pass", "provider key matches configuration"))
    else:
        evaluation.checks.append(
            _check("manifest.key", "fail", "provider key does not match configuration")
        )

    configured = tuple(sorted(expected_capabilities)) if expected_capabilities is not None else None
    if configured is None or manifest.capabilities == configured:
        evaluation.checks.append(
            _check("manifest.capabilities", "pass", "provider capabilities match configuration")
        )
    else:
        evaluation.checks.append(
            _check(
                "manifest.capabilities",
                "fail",
                "provider capabilities do not match configuration",
            )
        )

    declared_version = getattr(evaluation.module, "__version__", None)
    if declared_version is None:
        evaluation.checks.append(_check("manifest.version", "pass", "manifest version is authoritative"))
    elif isinstance(declared_version, str) and declared_version.strip() == manifest.version:
        evaluation.checks.append(
            _check("manifest.version", "pass", "module and manifest versions match")
        )
    else:
        evaluation.checks.append(
            _check("manifest.version", "fail", "module and manifest versions differ")
        )

    return True


def _factory(evaluation: _Evaluation, *, factory_name: str, instantiate: bool) -> bool:
    assert evaluation.module is not None
    factory = getattr(evaluation.module, factory_name, None)
    if not callable(factory):
        evaluation.checks.append(
            _check("factory.callable", "fail", "configured provider factory is not callable")
        )
        return False
    evaluation.checks.append(_check("factory.callable", "pass", "provider factory is callable"))

    if inspect.iscoroutinefunction(factory):
        evaluation.checks.append(
            _check("factory.sync", "fail", "asynchronous provider factories are unsupported")
        )
        return False
    evaluation.checks.append(_check("factory.sync", "pass", "provider factory is synchronous"))

    try:
        signature = inspect.signature(factory)
    except (TypeError, ValueError):
        evaluation.checks.append(
            _check("factory.signature", "fail", "provider factory signature is unavailable")
        )
        return False
    required = tuple(
        name
        for name, parameter in signature.parameters.items()
        if parameter.default is inspect.Parameter.empty
        and parameter.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    )
    if required:
        evaluation.checks.append(
            _check("factory.signature", "fail", "provider factory must not require arguments")
        )
        return False
    evaluation.checks.append(
        _check("factory.signature", "pass", "provider factory requires no arguments")
    )

    if not instantiate:
        evaluation.checks.append(
            _check("factory.result", "pass", "factory invocation deferred to runtime loading")
        )
        return True

    try:
        instance = factory()
    except Exception as exc:
        evaluation.checks.append(_check("factory.result", "fail", _safe_failure("provider factory", exc)))
        return False
    if inspect.isawaitable(instance):
        close = getattr(instance, "close", None)
        if callable(close):
            close()
        evaluation.checks.append(
            _check("factory.result", "fail", "provider factory returned an awaitable")
        )
        return False
    if instance is None:
        evaluation.checks.append(_check("factory.result", "fail", "provider factory returned None"))
        return False
    evaluation.instance = instance
    evaluation.checks.append(_check("factory.result", "pass", "provider factory returned an instance"))
    return True


def _method_signature(
    instance: Any,
    *,
    capability: str,
    method_name: str,
    expected_parameters: tuple[str, ...],
    checks: list[ConformanceCheck],
) -> None:
    method = getattr(instance, method_name, None)
    code = f"capability.{capability}.{method_name}"
    if not callable(method):
        checks.append(_check(code, "fail", f"required method '{method_name}' is missing"))
        return
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        checks.append(_check(code, "fail", f"method '{method_name}' signature is unavailable"))
        return

    parameters = signature.parameters
    missing = tuple(name for name in expected_parameters if name not in parameters)
    required_extras = tuple(
        name
        for name, parameter in parameters.items()
        if name not in expected_parameters
        and parameter.default is inspect.Parameter.empty
        and parameter.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    )
    if missing or required_extras:
        checks.append(_check(code, "fail", f"method '{method_name}' has an incompatible signature"))
        return
    checks.append(_check(code, "pass", f"method '{method_name}' signature conforms"))


def _validate_instance(evaluation: _Evaluation) -> None:
    assert evaluation.manifest is not None
    assert evaluation.instance is not None

    name = getattr(evaluation.instance, "name", None)
    if not isinstance(name, str) or not name.strip():
        evaluation.checks.append(
            _check("provider.name", "fail", "provider instance must define a non-empty name")
        )
    else:
        evaluation.checks.append(_check("provider.name", "pass", "provider name is present"))

    for capability in evaluation.manifest.capabilities:
        for method_name, parameters in CAPABILITY_PARAMETERS[capability].items():
            _method_signature(
                evaluation.instance,
                capability=capability,
                method_name=method_name,
                expected_parameters=parameters,
                checks=evaluation.checks,
            )


def _evaluate_provider(
    module_or_name: str | ModuleType,
    *,
    expected_key: str | None,
    expected_capabilities: tuple[str, ...] | None,
    api_version: str,
    instantiate: bool,
    factory_name: str | None,
) -> _Evaluation:
    evaluation = _Evaluation(module=None, manifest=None, instance=None, checks=[])
    if not _import_module(module_or_name, evaluation):
        return evaluation
    if not _validate_manifest(
        evaluation,
        expected_key=expected_key,
        expected_capabilities=expected_capabilities,
        api_version=api_version,
    ):
        return evaluation
    assert evaluation.manifest is not None
    selected_factory = factory_name or evaluation.manifest.factory
    if selected_factory != evaluation.manifest.factory:
        evaluation.checks.append(
            _check("factory.manifest", "fail", "requested factory differs from provider manifest")
        )
        return evaluation
    evaluation.checks.append(_check("factory.manifest", "pass", "provider factory matches manifest"))
    if not _factory(evaluation, factory_name=selected_factory, instantiate=instantiate):
        return evaluation
    if instantiate:
        _validate_instance(evaluation)
    else:
        assert evaluation.module is not None
        factory = getattr(evaluation.module, selected_factory)
        try:
            return_annotation = get_type_hints(factory, globalns=vars(evaluation.module)).get("return")
        except (NameError, TypeError):
            return_annotation = None
        provider_type = return_annotation if isinstance(return_annotation, type) else None
        if provider_type is not None:
            try:
                structural_instance = object.__new__(provider_type)
            except TypeError:
                structural_instance = None
            if structural_instance is not None:
                evaluation.instance = structural_instance
                _validate_instance(evaluation)
                evaluation.instance = None
            else:
                evaluation.checks.append(
                    _check(
                        "provider.structure",
                        "warning",
                        "provider type cannot be inspected without runtime construction",
                    )
                )
        else:
            evaluation.checks.append(
                _check(
                    "provider.structure",
                    "warning",
                    "factory return annotation is unavailable; runtime loading completes interface checks",
                )
            )
    return evaluation


def inspect_provider_module(
    module_or_name: str | ModuleType,
    *,
    expected_key: str | None = None,
    expected_capabilities: tuple[str, ...] | None = None,
    api_version: str = "0.0.0",
    instantiate: bool = False,
    factory_name: str | None = None,
) -> ProviderConformanceReport:
    """Inspect one provider package without invoking data or network methods."""

    evaluation = _evaluate_provider(
        module_or_name,
        expected_key=expected_key,
        expected_capabilities=expected_capabilities,
        api_version=api_version,
        instantiate=instantiate,
        factory_name=factory_name,
    )
    return ProviderConformanceReport(
        module=_module_name(module_or_name),
        checks=tuple(evaluation.checks),
        manifest=evaluation.manifest,
    )


def load_conforming_provider(
    module_or_name: str | ModuleType,
    *,
    expected_key: str,
    expected_capabilities: tuple[str, ...],
    api_version: str,
    factory_name: str | None = None,
) -> ConformingProvider:
    """Instantiate a provider only after all required conformance checks pass."""

    evaluation = _evaluate_provider(
        module_or_name,
        expected_key=expected_key,
        expected_capabilities=expected_capabilities,
        api_version=api_version,
        instantiate=True,
        factory_name=factory_name,
    )
    report = ProviderConformanceReport(
        module=_module_name(module_or_name),
        checks=tuple(evaluation.checks),
        manifest=evaluation.manifest,
    )
    if not report.passed or evaluation.manifest is None or evaluation.instance is None:
        raise ProviderConformanceError(report)
    return ConformingProvider(
        instance=evaluation.instance,
        manifest=evaluation.manifest,
        report=report,
    )
