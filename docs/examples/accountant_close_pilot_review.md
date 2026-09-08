# Accountant close pilot review worksheet

Status: **NOT RUN — no human or browser acceptance is recorded in this template.**

Use only the synthetic [controlled month-end close](accountant_month_end_close.md). Record what happened, not what the automated rehearsal is expected to prove. Keep credentials, raw personal paths, customer financial records and authentication headers out of shared evidence.

## Run identity

| Field | Observation |
| --- | --- |
| Source HEAD and tree | NOT RECORDED |
| Branch, PR and base | NOT RECORDED |
| Python / Streamlit and requirement compliance | NOT RECORDED |
| Browser version and viewport | NOT RECORDED |
| API/UI loopback ports | NOT RECORDED |
| Fresh synthetic database confirmed | NOT RECORDED |
| Roles exercised: preparer, reviewer, administrator | NOT RECORDED |
| Automated `close-pilot.json` reference | NOT RECORDED |

## Workflow observations

For each step record PASS, FAIL, BLOCKED or NOT RUN, plus a short observation and evidence reference. A tooling limitation is BLOCKED, not an invented product failure or an automatic PASS.

| Step | Result | Observation / evidence |
| --- | --- | --- |
| Fresh-database setup and three-user sign-in | NOT RUN | |
| Initial blockers are understandable and actionable | NOT RUN | |
| Draft evidence is generated, recorded and downloaded | NOT RUN | |
| Staged adjustment produces cash 355 / revenue -500 / payroll 145 | NOT RUN | |
| Prior evidence and reconciliations become stale after posting | NOT RUN | |
| Both reconciliations are refreshed and independently approved | NOT RUN | |
| Current variance run replaces stale review input | NOT RUN | |
| Both material rows receive explanation and reviewer notes | NOT RUN | |
| Journal request/decision history correctly distinguishes actors | NOT RUN | |
| Freshness attestation and READY transition | NOT RUN | |
| READY posting is rejected without partial writes | NOT RUN | |
| Administrator closes and downloads current CLOSED evidence | NOT RUN | |
| Repeated unchanged final download has the same digest | NOT RUN | |
| CLOSED posting is rejected without partial writes | NOT RUN | |
| Explicit reopen makes final evidence historical/stale | NOT RUN | |
| Relevant controls remain usable by keyboard and at narrow viewport | NOT RUN | |

## Friction and usefulness

Record measured setup/completion time only when actually observed. Do not substitute automated test duration for time spent by an accountant. Do not assign an overall score without a reviewer.

| Question | Reviewer observation |
| --- | --- |
| Which setup step required assistance? | NOT OBSERVED |
| Which blocker or next action was unclear? | NOT OBSERVED |
| Which role switch or data refresh was unnecessary or confusing? | NOT OBSERVED |
| Could the reviewer trace the expected balance to the posted adjustment? | NOT OBSERVED |
| Could the reviewer distinguish draft, final and reopened evidence? | NOT OBSERVED |
| Which evidence file would actually help a close review? | NOT OBSERVED |
| What is missing before a sanitized historical-data pilot is useful? | NOT OBSERVED |
| Observed setup / workflow time and measurement method | NOT OBSERVED |

## Defect and follow-up record

For an observed defect, record the stage, exact source, expected/actual behavior, sanitized evidence, reproducibility and whether it prevents this controlled close. Fix gaps exposed by this pilot; do not convert unrelated wishes into release blockers or broaden accounting policy silently.

Outcome: **NOT RUN**. No production, security, financial-reporting or regulatory approval is implied.

## Preservation

Record the deliberately retained synthetic database, task-local environment, result files and logs. Confirm pre-existing worktrees, environments, database and prior PR evidence were preserved. Do not delete or overwrite them as an incidental closeout step. A retained, identified evidence directory is an explained disposition, not a reason to force cleanup.
