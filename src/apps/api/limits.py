"""Central application resource limits for inbound requests and local uploads."""

from __future__ import annotations

# Keep individual HTTP requests small enough for predictable application memory use.
MAX_REQUEST_BODY_BYTES = 2 * 1024 * 1024
# Streamlit uploads are retained in session state, so use a stricter per-file cap.
MAX_UPLOAD_BYTES = 1 * 1024 * 1024

# Statistical work scales with observations, regressors, models, and forecast windows.
MAX_SERIES_POINTS = 10_000
MAX_REGRESSOR_FIELDS = 32
MAX_MODELS_PER_BACKTEST = 16
MAX_FORECAST_HORIZON = 365

# Scenario execution can fan out into provider and jurisdiction work.
MAX_SCENARIOS_PER_BATCH = 100
MAX_SYMBOLS_PER_SCENARIO = 64
MAX_JURISDICTIONS_PER_SCENARIO = 64
MAX_TAGS_PER_OBJECT = 64
MAX_TAG_LENGTH = 128

# Workflow ingestion writes and validates every submitted record.
MAX_WORKFLOW_TRANSACTIONS = 100
MAX_POSTINGS_PER_TRANSACTION = 100
MAX_STAGED_IDS_PER_REQUEST = 500

# Metadata is intentionally flexible, but its shape must remain cheap to validate and store.
MAX_METADATA_DEPTH = 6
MAX_METADATA_KEYS_PER_MAPPING = 128
MAX_METADATA_TOTAL_NODES = 2_048
MAX_METADATA_STRING_LENGTH = 4_096

# Common identifier and display-string limits keep validation policy consistent.
MAX_NAME_LENGTH = 255
MAX_SOURCE_LENGTH = 128
MAX_SOURCE_REFERENCE_LENGTH = 255
MAX_MODEL_KEY_LENGTH = 128
MAX_DESCRIPTION_LENGTH = 4_096
MAX_SCHEDULE_LENGTH = 255
MAX_ACCOUNT_CODE_LENGTH = 64
MAX_CURRENCY_LENGTH = 12

# Accountant close workspace hard limits. Configuration may tighten these
# values, but API schemas and services must never accept values above them.
MAX_PERIOD_LABEL_LENGTH = 120
MAX_CLOSE_NAME_LENGTH = 160
MAX_CLOSE_NOTES_LENGTH = 4_096
MAX_TRANSITION_REASON_LENGTH = 1_000
MAX_CHECKLIST_TITLE_LENGTH = 200
MAX_CHECKLIST_DESCRIPTION_LENGTH = 2_000
MAX_CHECKLIST_NOTES_LENGTH = 2_000
MAX_CUSTOM_CLOSE_TASKS = 50
MAX_RECONCILIATIONS_PER_CYCLE = 500
MAX_RECONCILIATION_NOTES_LENGTH = 4_096
MAX_VARIANCE_REVIEW_ROWS = 5_000
MAX_APPROVAL_COMMENT_LENGTH = 2_000
MAX_CLOSE_LIST_PAGE = 500
MAX_EVIDENCE_ROWS = 20_000
MAX_EVIDENCE_ARCHIVE_BYTES = 8 * 1024 * 1024
