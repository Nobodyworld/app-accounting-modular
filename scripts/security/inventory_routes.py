"""Generate the post-UX FastAPI route and authorization inventory."""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Avoid host database writes and external tracing while importing the application.
os.environ.setdefault("MODACCT_DATABASE_URL", "sqlite://")
os.environ.setdefault("MODACCT_LOG_DESTINATION", "null")
os.environ.setdefault("MODACCT_TRACING_EXPORTER", "disabled")

from apps.api.main import app  # noqa: E402
from apps.observability.tracing import configure_tracing  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.dependencies.utils import get_dependant  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402

configure_tracing("security-route-inventory", exporter="disabled")

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True, slots=True)
class Policy:
    classification: str
    identifiers: str
    data: str
    negative_tests: str
    missing_tests: str


POLICIES: dict[str, Policy] = {
    "GET /health": Policy(
        "public",
        "none",
        "health, provider descriptors, database and scheduler status",
        "tests/test_core_health.py; tests/test_health_endpoints.py",
        "public error-detail redaction",
    ),
    "GET /providers": Policy(
        "public",
        "none",
        "provider keys, modules, versions, capabilities, compatibility",
        "tests/test_plugin_loader.py",
        "anonymous information-disclosure policy",
    ),
    "POST /auth/token": Policy(
        "public",
        "username",
        "credentials in; access/refresh tokens and session id out; login audit write",
        "tests/test_security_integration.py",
        "malformed Authorization is not applicable; distributed rate-limit behavior",
    ),
    "GET /audit/": Policy(
        "tenant administrator",
        "organization_id, user_id, request_id, after_id",
        "tenant-scoped audit records (read)",
        "tests/test_audit_api.py",
        "inactive organization is covered indirectly; audit denial-entry policy",
    ),
    "GET /health/live": Policy(
        "public",
        "none",
        "process liveness",
        "tests/test_health_endpoints.py",
        "none identified",
    ),
    "GET /health/ready": Policy(
        "public",
        "none",
        "health-check details",
        "tests/test_health_endpoints.py",
        "upstream exception redaction",
    ),
    "GET /health/metrics": Policy(
        "public",
        "none",
        "Prometheus metrics",
        "tests/test_health_endpoints.py",
        "anonymous metadata-disclosure policy",
    ),
    "GET /health/telemetry": Policy(
        "public",
        "none",
        "metrics, health reports, extension modules and state",
        "tests/test_health_endpoints.py",
        "anonymous information-disclosure policy",
    ),
    "GET /extensions/contracts": Policy(
        "public",
        "none",
        "configured extension contracts and module metadata",
        "tests/test_extensions_api.py",
        "anonymous information-disclosure policy",
    ),
    "POST /ledger/account": Policy(
        "tenant manager",
        "organization_id",
        "ledger account (create)",
        "tests/test_security_integration.py; tests/test_ledger_api_invariants.py",
        "explicit no-membership and inactive-organization cases",
    ),
    "POST /ledger/post": Policy(
        "tenant manager",
        "organization_id, account_id, source_reference",
        "transaction and postings (create)",
        "tests/test_ledger_api_invariants.py; tests/test_ledger_service.py",
        "concurrent duplicate source_reference API requests",
    ),
    "GET /ledger/trial-balance": Policy(
        "tenant manager",
        "organization_id",
        "tenant accounts, postings, and balances (read)",
        "tests/test_security_integration.py; tests/test_ledger_api_invariants.py",
        "inactive organization and stale membership state",
    ),
    "POST /fx/sync": Policy(
        "tenant manager",
        "organization_id, provider_key",
        "provider FX data (read external, write tenant rates, schedule backfill)",
        "tests/test_fx_api.py; tests/test_security_integration.py",
        "upstream response-size and timeout-failure API cases",
    ),
    "POST /market/sync": Policy(
        "tenant manager",
        "organization_id, provider_key, symbol",
        "provider market data (read external, write tenant prices)",
        "tests/test_security_integration.py",
        "authorization-before-provider-discovery; malformed upstream payload",
    ),
    "GET /snapshot": Policy(
        "authenticated only",
        "provider selection is implicit; no organization identifier",
        "shared provider snapshot and cache (read)",
        "tests/test_snapshot_api.py",
        "wrong token type; resource bounds on repeated query values",
    ),
    "POST /snapshot/scenarios": Policy(
        "authenticated only",
        "scenario names and provider inputs; no organization identifier",
        "shared scenario snapshot/cache (read and mutate cache)",
        "tests/test_snapshot_api.py; tests/test_data_snapshot_service.py",
        "scenario-count and nested-metadata bounds",
    ),
    "POST /snapshot/plans/preview": Policy(
        "authenticated only",
        "scenario plan names/defaults; no organization identifier",
        "validated plan summary (read/compute)",
        "tests/test_snapshot_api.py; tests/test_scenario_plan_api_defaults.py",
        "payload-size/depth and duplicate-key policy",
    ),
    "POST /tax/sync": Policy(
        "tenant manager",
        "organization_id, provider_key",
        "provider tax data (read external, write/delete tenant tax rules)",
        "tests/test_security_integration.py; tests/test_tax_service.py",
        "authorization-before-provider-discovery",
    ),
    "POST /forecast/series": Policy(
        "tenant member",
        "organization_id",
        "caller-supplied series (compute forecast)",
        "tests/test_forecast_service.py",
        "route-level no-membership and collection/CPU bounds",
    ),
    "GET /forecast/models": Policy(
        "tenant member",
        "organization_id",
        "forecast model catalog (read)",
        "tests/test_forecast_service.py",
        "route-level no-membership",
    ),
    "POST /forecast/backtest": Policy(
        "tenant member",
        "organization_id",
        "caller-supplied series (compute backtests)",
        "tests/test_forecast_service.py",
        "route-level no-membership and collection/CPU bounds",
    ),
    "POST /forecast/impact": Policy(
        "tenant member",
        "organization_id",
        "caller-supplied series (compute causal impact)",
        "tests/test_forecast_service.py",
        "route-level no-membership, date-range, and collection/CPU bounds",
    ),
    "GET /reports/budget-vs-actual": Policy(
        "tenant member",
        "organization_id, budget_id",
        "tenant budget, ledger, forecast, cached report, CSV export (read/write cache)",
        "tests/test_reports_api.py; tests/test_reports_pagination.py",
        "CSV formula injection and inactive organization",
    ),
    "GET /reports/cashflow-forecast": Policy(
        "tenant member",
        "organization_id",
        "tenant cashflow, forecast, cached report, CSV export (read/write cache)",
        "tests/test_reports_api.py; tests/test_reports_cache.py; tests/test_reports_streaming.py",
        "CSV formula injection and stale membership state",
    ),
    "POST /workflow/ingest": Policy(
        "tenant manager",
        "organization_id, account_id, source_reference",
        "staged transactions/postings and optional ledger posting (create)",
        "tests/test_workflow_api.py",
        "transaction/posting count and metadata-depth bounds",
    ),
    "POST /workflow/process": Policy(
        "tenant manager",
        "organization_id, staged_id",
        "staged transactions and ledger postings (read/update/create)",
        "tests/test_workflow_api.py",
        "concurrent processing of identical staged ids",
    ),
    "GET /workflow/{staged_id}": Policy(
        "tenant manager",
        "organization_id, staged_id",
        "tenant staged transaction and postings (read)",
        "tests/test_workflow_api.py",
        "inactive organization and stale membership state",
    ),
    "GET /workflow": Policy(
        "tenant manager",
        "organization_id",
        "tenant staged transactions and postings (read)",
        "tests/test_workflow_api.py",
        "large-dataset scan behavior",
    ),
    "GET /workflow/": Policy(
        "tenant manager",
        "organization_id",
        "tenant staged transactions and postings (read; schema-hidden alias)",
        "tests/test_workflow_api.py",
        "large-dataset scan behavior",
    ),
}

FRAMEWORK_POLICIES: dict[str, Policy] = {
    "GET /openapi.json": Policy("public", "none", "OpenAPI schema", "framework-generated", "schema exposure policy"),
    "HEAD /openapi.json": Policy("public", "none", "OpenAPI schema", "framework-generated", "schema exposure policy"),
    "GET /docs": Policy("public", "none", "Swagger UI", "framework-generated", "documentation exposure policy"),
    "HEAD /docs": Policy("public", "none", "Swagger UI", "framework-generated", "documentation exposure policy"),
    "GET /docs/oauth2-redirect": Policy(
        "public", "none", "Swagger OAuth2 redirect", "framework-generated", "documentation exposure policy"
    ),
    "HEAD /docs/oauth2-redirect": Policy(
        "public", "none", "Swagger OAuth2 redirect", "framework-generated", "documentation exposure policy"
    ),
    "GET /redoc": Policy("public", "none", "ReDoc UI", "framework-generated", "documentation exposure policy"),
    "HEAD /redoc": Policy("public", "none", "ReDoc UI", "framework-generated", "documentation exposure policy"),
}


@dataclass(frozen=True, slots=True)
class InventoryRoute:
    method: str
    path: str
    module: str
    dependencies: tuple[str, ...]
    policy: Policy


def _call_name(call: Any) -> str:
    module = getattr(call, "__module__", type(call).__module__)
    name = getattr(call, "__qualname__", getattr(call, "__name__", type(call).__qualname__))
    return f"{module}.{name}"


def _walk_dependant(dependant: Any) -> Iterable[str]:
    call = getattr(dependant, "call", None)
    if call is not None:
        yield _call_name(call)
    for child in getattr(dependant, "dependencies", ()):
        yield from _walk_dependant(child)


def _dependency_names(route: APIRoute, inherited: Sequence[Any]) -> tuple[str, ...]:
    names = list(_walk_dependant(route.dependant))
    for dependency in inherited:
        call = getattr(dependency, "dependency", None)
        if call is None:
            continue
        try:
            dependant = get_dependant(path=route.path, call=call)
        except TypeError:
            names.append(_call_name(call))
        else:
            names.extend(_walk_dependant(dependant))
    endpoint_name = _call_name(route.endpoint)
    return tuple(dict.fromkeys(name for name in names if name != endpoint_name))


def _application_routes(application: FastAPI) -> list[InventoryRoute]:
    inventory: list[InventoryRoute] = []
    seen_policy_keys: set[str] = set()

    for wrapper in application.routes:
        if isinstance(wrapper, APIRoute):
            candidates = ((wrapper, ()),)
        elif type(wrapper).__name__ == "_IncludedRouter":
            original = wrapper.original_router
            inherited = tuple(wrapper.include_context.dependencies)
            candidates = ((route, inherited) for route in original.routes if isinstance(route, APIRoute))
        else:
            continue

        for route, inherited in candidates:
            for method in sorted(route.methods):
                key = f"{method} {route.path}"
                policy = POLICIES.get(key)
                if policy is None:
                    raise RuntimeError(f"unmapped application route: {key}")
                seen_policy_keys.add(key)
                inventory.append(
                    InventoryRoute(
                        method=method,
                        path=route.path,
                        module=_call_name(route.endpoint),
                        dependencies=_dependency_names(route, inherited),
                        policy=policy,
                    )
                )

    stale = set(POLICIES) - seen_policy_keys
    if stale:
        raise RuntimeError(f"policy entries without matching application routes: {sorted(stale)}")
    return inventory


def _framework_routes(application: FastAPI) -> list[InventoryRoute]:
    inventory: list[InventoryRoute] = []
    for route in application.routes:
        if isinstance(route, APIRoute) or type(route).__name__ == "_IncludedRouter":
            continue
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        endpoint = getattr(route, "endpoint", None)
        if path is None or methods is None or endpoint is None:
            continue
        for method in sorted(methods):
            key = f"{method} {path}"
            policy = FRAMEWORK_POLICIES.get(key)
            if policy is None:
                raise RuntimeError(f"unmapped framework route: {key}")
            inventory.append(InventoryRoute(method, path, _call_name(endpoint), (), policy))
    return inventory


def _git_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _escape(value: str) -> str:
    return value.replace("|", r"\|").replace("\n", " ")


def render_markdown(routes: Sequence[InventoryRoute]) -> str:
    counts: dict[str, int] = {}
    for route in routes:
        counts[route.policy.classification] = counts.get(route.policy.classification, 0) + 1

    lines = [
        "# FastAPI route and authorization inventory",
        "",
        f"- Tested commit: `{_git_sha()}`",
        f"- Operating system: `{platform.platform()}`",
        f"- Python: `{platform.python_version()}`",
        "- Generator: `scripts/security/inventory_routes.py`",
        "- Procedure: `python scripts/security/inventory_routes.py --output docs/security/evidence/route-inventory.md`",
        f"- Result: **PASS** — {len(routes)} method/path entries mapped; no unmapped application routes",
        "",
        "## Authorization totals",
        "",
        "| Classification | Method/path entries |",
        "|---|---:|",
    ]
    for classification in ("public", "authenticated only", "tenant member", "tenant manager", "tenant administrator"):
        lines.append(f"| {classification} | {counts.get(classification, 0)} |")

    lines.extend(
        [
            "",
            "The totals include FastAPI's four public documentation/schema paths with both GET and HEAD methods. "
            "The application itself exposes 29 method/path entries. “Tenant manager” means an active member with "
            "the route-specific management flag or `is_admin`; the API has no single generic manager role. "
            "UI gating is not counted as authorization evidence.",
            "",
            "## Complete inventory",
            "",
            "| Method | Path | Router / endpoint | Authorization | Identifiers | Data read or modified | "
            "Dependency chain | Existing negative tests | Missing negative tests |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for route in sorted(routes, key=lambda item: (item.path, item.method)):
        dependency_text = "<br>".join(route.dependencies) if route.dependencies else "none"
        lines.append(
            "| "
            + " | ".join(
                _escape(value)
                for value in (
                    route.method,
                    route.path,
                    route.module,
                    route.policy.classification,
                    route.policy.identifiers,
                    route.policy.data,
                    dependency_text,
                    route.policy.negative_tests,
                    route.policy.missing_tests,
                )
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Review notes",
            "",
            "- Router-level `authenticated_audit_context` is inherited by audit, ledger, FX, market, snapshot, tax, "
            "forecast, reports, and workflow routers.",
            "- Role checks are route-local calls to `get_current_organization`; they are therefore documented by the "
            "explicit policy map in the generator and are not inferred from UI state.",
            "- `/market/sync` and `/tax/sync` currently perform provider lookup before tenant authorization. This is "
            "tracked as an audit finding.",
            "- Snapshot routes require authentication but accept no organization identifier and operate on shared "
            "provider/cache state; they are not evidence of tenant-scoped data authorization.",
            "- Framework documentation, schema, health, metrics, provider, telemetry, and extension surfaces are "
            "public in code. Restricting them is a deployment control unless application middleware is added.",
            "",
        ]
    )
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="write Markdown to this path instead of stdout")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    routes = [*_framework_routes(app), *_application_routes(app)]
    markdown = render_markdown(routes)
    if args.output is None:
        print(markdown)
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(markdown, encoding="utf-8", newline="\n")
    print(f"Wrote {len(routes)} method/path entries to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
