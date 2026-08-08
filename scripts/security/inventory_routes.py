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
    "POST /auth/refresh": Policy(
        "public",
        "refresh token; session_id and jti token claims",
        "refresh token in; rotated access token, refresh token, and session id out; persisted session lookup, "
        "atomic one-time rotation, refresh-reuse detection, family revocation, and generic credential failures",
        "tests/test_auth_session_lifecycle.py::test_valid_refresh_rotates_and_reuse_revokes_complete_session; "
        "tests/test_auth_session_lifecycle.py::"
        "test_refresh_rejects_access_malformed_wrong_signature_and_missing_session; "
        "tests/test_token_type_boundary.py",
        "distributed concurrent rotation across non-coordinating database deployments",
    ),
    "POST /auth/logout": Policy(
        "authenticated only",
        "current access-token session",
        "server-side revocation of the current session; logout audit event; generic invalid-session response",
        "tests/test_auth_session_lifecycle.py::test_logout_revokes_current_session_and_invalidates_both_tokens; "
        "tests/test_streamlit_api_session.py::"
        "test_logout_failure_is_sanitized_and_local_clear_removes_all_session_state; "
        "tests/test_streamlit_app.py::test_logout_clears_only_api_session_and_relocks_protected_actions",
        "none identified",
    ),
    "POST /auth/sessions/{session_id}/revoke": Policy(
        "tenant administrator",
        "organization_id, session_id",
        "same-organization membership and administrator checks; nondisclosing 404 for missing or cross-tenant "
        "targets; idempotent server-side session revocation; audit event",
        "tests/test_auth_session_lifecycle.py::test_organization_admin_revocation_is_scoped_and_idempotent",
        "none identified",
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
        "tests/test_fx_api.py; tests/test_security_integration.py; tests/test_provider_network_boundaries.py",
        "none identified",
    ),
    "POST /market/sync": Policy(
        "tenant manager",
        "organization_id, provider_key, symbol",
        "provider market data (read external, write tenant prices)",
        "tests/test_security_integration.py; tests/test_provider_authorization_order.py; "
        "tests/test_market_yfinance_provider.py",
        "YFinance high-level client does not expose raw response-byte enforcement",
    ),
    "GET /snapshot": Policy(
        "authenticated only",
        "provider selection is implicit; no organization identifier",
        "shared provider snapshot and cache (read)",
        "tests/test_snapshot_api.py; tests/test_token_type_boundary.py",
        "none identified",
    ),
    "POST /snapshot/scenarios": Policy(
        "authenticated only",
        "scenario names and provider inputs; no organization identifier",
        "shared scenario snapshot/cache (read and mutate cache)",
        "tests/test_snapshot_api.py; tests/test_data_snapshot_service.py; tests/test_input_limits.py; "
        "tests/test_request_body_limits.py",
        "none identified",
    ),
    "POST /snapshot/plans/preview": Policy(
        "authenticated only",
        "scenario plan names/defaults; no organization identifier",
        "validated plan summary (read/compute)",
        "tests/test_snapshot_api.py; tests/test_scenario_plan_api_defaults.py; tests/test_input_limits.py; "
        "tests/test_request_body_limits.py",
        "duplicate JSON-key rejection is not implemented by the framework parser",
    ),
    "POST /tax/sync": Policy(
        "tenant manager",
        "organization_id, provider_key",
        "provider tax data (read external, write/delete tenant tax rules)",
        "tests/test_security_integration.py; tests/test_tax_service.py; tests/test_provider_authorization_order.py; "
        "tests/test_provider_network_boundaries.py",
        "none identified",
    ),
    "POST /forecast/series": Policy(
        "tenant member",
        "organization_id",
        "caller-supplied series (compute forecast)",
        "tests/test_forecast_service.py; tests/test_input_limits.py; tests/test_request_body_limits.py",
        "route-level no-membership",
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
        "tests/test_forecast_service.py; tests/test_input_limits.py; tests/test_request_body_limits.py",
        "route-level no-membership",
    ),
    "POST /forecast/impact": Policy(
        "tenant member",
        "organization_id",
        "caller-supplied series (compute causal impact)",
        "tests/test_forecast_service.py; tests/test_input_limits.py; tests/test_request_body_limits.py",
        "route-level no-membership",
    ),
    "GET /reports/budget-vs-actual": Policy(
        "tenant member",
        "organization_id, budget_id",
        "tenant budget, ledger, forecast, cached report, CSV export (read/write cache)",
        "tests/test_reports_api.py; tests/test_reports_pagination.py; tests/test_csv_export_safety.py",
        "inactive organization",
    ),
    "GET /reports/cashflow-forecast": Policy(
        "tenant member",
        "organization_id",
        "tenant cashflow, forecast, cached report, CSV export (read/write cache)",
        "tests/test_reports_api.py; tests/test_reports_cache.py; tests/test_reports_streaming.py; "
        "tests/test_csv_export_safety.py",
        "stale membership state",
    ),
    "POST /workflow/ingest": Policy(
        "tenant manager",
        "organization_id, account_id, source_reference",
        "staged transactions/postings and optional ledger posting (create)",
        "tests/test_workflow_api.py; tests/test_input_limits.py; tests/test_request_body_limits.py",
        "none identified",
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

POLICIES.update(
    {
        "POST /close/periods": Policy(
            "tenant ledger manager",
            "organization_id",
            "accounting period and posting-boundary metadata (create)",
            "tests/test_close_api.py; tests/test_close_service.py; tests/test_close_tenant_isolation.py",
            "cross-process overlap serialization beyond SQLite transaction guarantees",
        ),
        "GET /close/periods": Policy(
            "tenant member",
            "organization_id, limit, offset",
            "tenant accounting periods (read)",
            "tests/test_close_api.py",
            "none identified",
        ),
        "GET /close/periods/{period_id}": Policy(
            "tenant member",
            "organization_id, period_id",
            "tenant accounting period (read; nondisclosing scoped lookup)",
            "tests/test_close_api.py; tests/test_close_tenant_isolation.py",
            "none identified",
        ),
        "POST /close/periods/{period_id}/cycles": Policy(
            "tenant ledger manager",
            "organization_id, period_id",
            "close cycle, policy snapshot, and standard checklist (create)",
            "tests/test_close_api.py; tests/test_close_service.py",
            "none identified",
        ),
        "GET /close/periods/{period_id}/cycles": Policy(
            "tenant member",
            "organization_id, period_id",
            "tenant close cycles for a period (read)",
            "tests/test_close_api.py",
            "none identified",
        ),
        "GET /close/cycles/{cycle_id}": Policy(
            "tenant member",
            "organization_id, cycle_id",
            "tenant close-cycle overview (read)",
            "tests/test_close_api.py; tests/test_close_tenant_isolation.py",
            "none identified",
        ),
        "POST /close/cycles/{cycle_id}/start": Policy(
            "tenant ledger manager",
            "organization_id, cycle_id, version",
            "close-cycle lifecycle and audit state (update)",
            "tests/test_close_api.py; tests/test_close_service.py",
            "none identified",
        ),
        "POST /close/cycles/{cycle_id}/ready": Policy(
            "tenant ledger manager",
            "organization_id, cycle_id, version",
            "server-derived readiness transition and audit state (update)",
            "tests/test_close_readiness.py; tests/test_close_api.py",
            "none identified",
        ),
        "POST /close/cycles/{cycle_id}/close": Policy(
            "tenant administrator",
            "organization_id, cycle_id, version",
            "atomic close-cycle and accounting-period posting lock (update)",
            "tests/test_close_readiness.py; tests/test_period_posting_lock.py; tests/test_close_api.py",
            "cross-process writer scheduling beyond SQLite transaction guarantees",
        ),
        "POST /close/cycles/{cycle_id}/reopen": Policy(
            "tenant administrator",
            "organization_id, cycle_id, version",
            "explicit period reopen, reason, and evidence staleness (update)",
            "tests/test_close_readiness.py; tests/test_close_service.py",
            "none identified",
        ),
        "POST /close/cycles/{cycle_id}/cancel": Policy(
            "tenant administrator",
            "organization_id, cycle_id, version",
            "pre-close cancellation reason and lifecycle audit state (update)",
            "tests/test_close_api.py; tests/test_close_service.py",
            "none identified",
        ),
        "GET /close/cycles/{cycle_id}/readiness": Policy(
            "tenant member",
            "organization_id, cycle_id",
            "server-derived checklist, workflow, reconciliation, variance, approval, and evidence blockers (read)",
            "tests/test_close_readiness.py; tests/test_close_api.py",
            "none identified",
        ),
        "GET /close/cycles/{cycle_id}/checklist": Policy(
            "tenant member",
            "organization_id, cycle_id",
            "tenant close checklist and computed control status (read)",
            "tests/test_close_workspace.py; tests/test_close_api.py",
            "none identified",
        ),
        "POST /close/cycles/{cycle_id}/checklist": Policy(
            "tenant ledger manager",
            "organization_id, cycle_id",
            "bounded custom checklist task (create)",
            "tests/test_close_service.py; tests/test_close_workspace.py",
            "none identified",
        ),
        "PATCH /close/cycles/{cycle_id}/checklist/{task_id}": Policy(
            "tenant ledger manager; administrator for final approval",
            "organization_id, cycle_id, task_id, version",
            "manual attestation or custom checklist task (update)",
            "tests/test_close_readiness.py; tests/test_close_workspace.py",
            "none identified",
        ),
        "GET /close/cycles/{cycle_id}/reconciliations": Policy(
            "tenant member",
            "organization_id, cycle_id",
            "tenant account reconciliations and server-derived balances (read)",
            "tests/test_reconciliation_service.py; tests/test_close_workspace.py",
            "none identified",
        ),
        "POST /close/cycles/{cycle_id}/reconciliations": Policy(
            "tenant ledger manager",
            "organization_id, cycle_id, account_id",
            "account reconciliation with server-derived ledger balance (create)",
            "tests/test_reconciliation_service.py",
            "none identified",
        ),
        "PATCH /close/cycles/{cycle_id}/reconciliations/{reconciliation_id}": Policy(
            "tenant ledger manager",
            "organization_id, cycle_id, reconciliation_id, version",
            "account reconciliation preparation and exception evidence (update)",
            "tests/test_reconciliation_service.py",
            "none identified",
        ),
        "POST /close/cycles/{cycle_id}/reconciliations/{reconciliation_id}/approve": Policy(
            "tenant ledger manager; independent actor",
            "organization_id, cycle_id, reconciliation_id, version",
            "independent reconciliation approval evidence (update)",
            "tests/test_reconciliation_service.py",
            "none identified",
        ),
        "POST /close/cycles/{cycle_id}/variance-reviews/from-budget": Policy(
            "tenant ledger manager",
            "organization_id, cycle_id, budget_id",
            "bounded materialized BudgetService report rows and provenance (create)",
            "tests/test_variance_review_service.py",
            "none identified",
        ),
        "GET /close/cycles/{cycle_id}/variance-reviews": Policy(
            "tenant member",
            "organization_id, cycle_id",
            "tenant variance review rows and dispositions (read)",
            "tests/test_variance_review_service.py; tests/test_close_workspace.py",
            "none identified",
        ),
        "PATCH /close/cycles/{cycle_id}/variance-reviews/{review_id}": Policy(
            "tenant ledger manager",
            "organization_id, cycle_id, review_id, version",
            "bounded material-variance disposition and reviewer note (update)",
            "tests/test_variance_review_service.py",
            "none identified",
        ),
        "POST /close/cycles/{cycle_id}/journal-approvals": Policy(
            "tenant ledger manager",
            "organization_id, cycle_id, transaction or staged_transaction reference",
            "journal approval request with trusted requestor identity (create)",
            "tests/test_journal_approval_service.py",
            "none identified",
        ),
        "GET /close/cycles/{cycle_id}/journal-approvals": Policy(
            "tenant member",
            "organization_id, cycle_id",
            "tenant journal approval state and immutable decision history (read)",
            "tests/test_journal_approval_service.py; tests/test_close_workspace.py",
            "none identified",
        ),
        "POST /close/cycles/{cycle_id}/journal-approvals/{approval_id}/decide": Policy(
            "tenant ledger manager; administrator for revocation; independent actor for approval",
            "organization_id, cycle_id, approval_id, version",
            "append-only approval decision and current state (update)",
            "tests/test_journal_approval_service.py",
            "none identified",
        ),
        "GET /close/cycles/{cycle_id}/evidence/preview": Policy(
            "tenant member",
            "organization_id, cycle_id",
            "bounded evidence file plan, manifest metadata, and freshness (read)",
            "tests/test_close_evidence.py; tests/test_close_workspace.py",
            "none identified",
        ),
        "POST /close/cycles/{cycle_id}/evidence": Policy(
            "tenant ledger manager",
            "organization_id, cycle_id",
            "deterministic evidence computation, manifest metadata, and audit reference (create)",
            "tests/test_close_evidence.py",
            "none identified",
        ),
        "GET /close/cycles/{cycle_id}/evidence/download": Policy(
            "tenant ledger manager",
            "organization_id, cycle_id",
            "bounded deterministic ZIP assembled in memory (read)",
            "tests/test_close_evidence.py; tests/test_close_workspace.py",
            "none identified",
        ),
    }
)

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
    framework_paths = {key.split(" ", 1)[1] for key in FRAMEWORK_POLICIES}

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
            f"The totals include {len(FRAMEWORK_POLICIES)} method/path entries across {len(framework_paths)} "
            "FastAPI documentation/schema paths. "
            f"The application itself exposes {len(POLICIES)} method/path entries. “Tenant manager” means an active "
            "member with "
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
            "- `/market/sync` and `/tax/sync` authorize organization membership and route-specific management "
            "permission before provider discovery; cross-tenant requests cannot use provider state as an oracle.",
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
