# tools/

Automation utilities and release helpers used during development.

- `audit_metrics.py` – Generates coverage, complexity, and dependency snapshots surfaced in `docs/reports/`.
- `coverage_gate.py` – Enforces the repository-wide 85% release-authoritative line floor.
- `critical_coverage.py` – Enforces independent line and branch floors from `config/critical-coverage.toml`; missing files or missing branch evidence fail closed.
- `diff_coverage.py` – Compares Coverage.py JSON evidence with added or modified executable production lines from an explicit Git base/head pair. It writes deterministic JSON and Markdown evidence and enforces `config/diff-coverage.toml`.
- `quality_gate.py` – Runs the consolidated lint, format, typing, test, accounting-control, dependency, and secret checks.
- `release.py` / `release_manager.py` – Support the `make release` workflow for semver bumps and changelog updates.

## Ruff policy

The quality gate invokes:

```bash
python -m ruff check .
python -m ruff format --check .
```

Ruff is pinned exactly to `0.16.0`. `pyproject.toml` explicitly selects the
reviewed lint families and limits discovery to Python/stub files plus the
configuration file. Markdown and notebooks are excluded, preview behavior is
disabled, and `force-exclude` prevents an explicit path from bypassing the
repository policy. See
[`docs/quality/ruff-0.16-migration.md`](../../docs/quality/ruff-0.16-migration.md).

## Changed-production-line coverage

Run the normal quality gate first so `coverage.json` exists, then provide an explicit base SHA or ref:

```bash
python -m src.tools.quality_gate
python -m src.tools.diff_coverage coverage.json \
  --base <base-sha-or-ref> \
  --head HEAD \
  --config config/diff-coverage.toml \
  --json-output diff-coverage.json \
  --markdown-output diff-coverage.md
```

The equivalent Make target regenerates coverage before evaluating the diff:

```bash
make diff-coverage BASE=<base-sha-or-ref>
```

The tool resolves the supplied base and head to commit SHAs, computes their merge base, evaluates only configured production roots, and intersects changed line numbers with Coverage.py's executable-line evidence. Deleted, blank, comment-only, and documentation-only lines do not enter the denominator. A changed production file missing from coverage evidence, malformed evidence, or an unresolved base fails closed. A diff with no changed executable production lines is reported explicitly as not applicable and passes by policy.

Pull-request CI uses the exact `github.event.pull_request.base.sha` and `github.event.pull_request.head.sha`; it does not infer a mutable branch name. The dedicated workflow uploads `coverage.json`, `diff-coverage.json`, and `diff-coverage.md` for review.

Each script is import-safe; reference [docs/operations/automation_playbook.md](../../docs/operations/automation_playbook.md) for guidance on when to run them.
