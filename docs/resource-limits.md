# Application Resource Limits

Modular Accounting applies deterministic inbound limits before expensive
validation, persistence, parsing, or statistical work. The central policy is
defined in `src/apps/api/limits.py`; schemas, middleware, and Streamlit upload
helpers import those names instead of maintaining independent numeric values.

## HTTP request bodies

The FastAPI default is 2 MiB (`2,097,152` bytes). Operators may set
`MODACCT_MAX_REQUEST_BODY_BYTES` to a positive integer no greater than that
default. The application checks a valid `Content-Length` immediately and also
counts the ASGI receive stream, so missing, false, invalid, or chunked length
metadata cannot bypass the limit.

An oversized body returns:

```http
HTTP/1.1 413 Payload Too Large
Content-Type: application/json

{"detail":"Request body exceeds the configured limit."}
```

The response never includes body content, request headers, secrets, or a stack
trace. The limiter is inside request metrics, request-context, and tracing
middleware, allowing the sanitized `413` status to remain observable without
logging the rejected bytes.

Every deployed reverse proxy, ingress, gateway, and load balancer must enforce
an equal or smaller request-body cap. The application boundary is defense in
depth and does not replace an edge limit.

## Schema limits

Requests that decode within the body cap but violate a Pydantic constraint
return FastAPI's standard deterministic `422 Unprocessable Entity` response.
Its `detail` value is a list of validation entries containing the field
location, validation message, submitted value, and constraint context. Clients
must use the status and field location rather than depending on Pydantic's
human-readable wording.

| Input | Maximum |
| --- | ---: |
| Forecast, backtest, or causal-impact series | 10,000 points |
| Regressor/intervention fields | 32 |
| Points in each regressor/intervention series | 10,000 |
| Backtest models | 16 |
| Forecast/backtest horizon | 365 |
| Backtest initial window or step | 10,000 |
| Scenarios in a direct batch or plan | 100 |
| Commodity symbols per scenario | 64 |
| Jurisdictions per scenario | 64 |
| Tags per object | 64 |
| Characters per tag | 128 |
| Workflow transactions | 100 |
| Postings per staged transaction | 100 |
| Staged IDs per process request, before deduplication | 500 |
| Accounting period label | 120 characters |
| Close-cycle name | 160 characters |
| Close/checklist/reconciliation notes | 2,000–4,096 characters by field |
| Transition reason | 1,000 characters |
| Custom close tasks per cycle | 50 |
| Reconciliations per cycle | 500 |
| Variance review rows per materialization | 5,000 |
| Journal approvals per cycle | 500 |
| Default close list page | 100 records |
| Close evidence rows | 20,000 |
| Close evidence ZIP | 8 MiB |
| Maximum close list page | 500 records |

Reconciliation, current-variance, approval-summary, and approval-decision reads use `limit`/`offset`; their accepted limit is `1..500` and their default is 100. Approval summaries omit nested history, which is available only through its independently paged route. The 500th durable approval may be created; a new distinct reference after that is rejected before any approval, decision, audit, or revision mutation.

Close evidence row and archive limits are enforced while the deterministic bundle is assembled in memory. Trial-balance rows and only deduplicated, sorted reconciliation account references participate in the shared row budget; there is no second organization-wide account lookup. A rejected bundle is not persisted. Close policy uses a fixed typed schema with bounded override reasons and account IDs; reconciliation evidence metadata uses the shared metadata validator below. Configuration may tighten but may not raise these hard maxima.

Names are limited to 255 characters, source names to 128, source references to
255, and forecast model keys to 128. Currency strings retain the existing
12-character schema maximum; account codes retain 64 characters. These are
upper bounds only and do not weaken existing semantic checks such as
forecast-series length relative to horizon, strict direct-scenario fields,
workflow account references, or accounting balancing controls.

Accounting `Decimal` precision semantics are unchanged. The global body limit
already bounds serialized digit input, and no repository use case justified a
new digit constraint that might alter valid accounting values.

## Metadata

One iterative validator covers workflow, staged transaction, staged posting,
scenario-plan parameter, and scenario-plan default metadata. It preserves
accepted values and rejects unsupported Python object types at the API boundary.
Accepted values are JSON-compatible mappings with string keys, lists, and
scalar values.

| Metadata dimension | Maximum |
| --- | ---: |
| Nesting depth (root is depth zero) | 6 |
| Keys in any mapping | 128 |
| Total value nodes, including containers | 2,048 |
| Characters in any key or string value | 4,096 |

The traversal is iterative, so adversarial nesting cannot overflow Python
recursion before the configured depth check.

## Streamlit uploads

Budget CSV and scenario-plan JSON/TOML/TML files share a 1 MiB
(`1,048,576`-byte) application limit. Streamlit's reported `UploadedFile.size`
is checked before `getvalue()`. When a size is unavailable, the helper reads at
most `limit + 1` bytes. Rejected files are not parsed and their bytes, previews,
names, and associated results are removed from session state. Retained
session-state bytes are checked again before parsing.

`.streamlit/config.toml` sets Streamlit's `server.maxUploadSize` to 2 decimal
megabytes as a framework-level defense. The stricter 1 MiB application check
remains authoritative and is required even if the framework configuration is
raised by a deployment.

Scenario-plan files remain local input until the user requests a preview. The
preview continues to use the authenticated, organization-scoped API boundary.

## Scope

These controls cover inbound application work only. Limits and retry policy for
responses received from external network providers are separate trust-boundary
work tracked by issue
[#118](https://github.com/Nobodyworld/app-accounting-modular/issues/118).
This remediation does not claim to resolve that issue.
