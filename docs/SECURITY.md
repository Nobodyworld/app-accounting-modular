# Security Policy

## Supported Versions

| Version | Supported |
| --- | --- |
| `main` | Best-effort Early Beta support |
| Tagged releases | None published |

## Reporting a Vulnerability

Use the repository's **Security** tab and select **Report a vulnerability** to submit a private report through GitHub Private Vulnerability Reporting.

Include reproduction steps, an impact assessment, affected versions or commits, and proof-of-concept material when it can be shared safely. Do not include vulnerability details in a public issue, pull request, discussion, or commit.

Response and remediation timing depends on severity, reproducibility, maintainer availability, and the scope of the Early Beta. No fixed response-time or remediation-time guarantee is provided.

## Coordinated Disclosure

- Keep the report private until a fix, mitigation, or disclosure plan is agreed.
- Security advisories may be coordinated and published through GitHub Security Advisories.
- Reporter credit may be provided with consent.
- Avoid accessing, modifying, or retaining data that is not necessary to demonstrate the issue.

## Hardening Checklist

- Rotate API keys and secrets regularly; never commit secrets to the repository.
- Run `pre-commit run --all-files` for formatting and static checks.
- Run `python -m src.tools.secret_scan` for the repository's lightweight
  current-tree secret pattern check.
- Before public release, run Gitleaks or an equivalent full-history scanner and
  record the tool version, command, commits scanned, findings, false-positive
  disposition, and final result in [`../PUBLIC_RELEASE_AUDIT.md`](../PUBLIC_RELEASE_AUDIT.md).
- Use environment variables (see `config/.env.example`) to configure sensitive settings.
- Review [`DEPENDENCIES.md`](DEPENDENCIES.md) quarterly for updated
  security posture notes and dependency audit status.
- Audit startup failure logs for sensitive payloads; `StartupManager` surfaces
  exception metadata for diagnostics, so ensure startup steps raise errors
  without embedding secrets or personal data.
