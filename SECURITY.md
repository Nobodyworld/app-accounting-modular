# Security Policy

## Supported Versions
| Version | Supported |
| ------- | --------- |
| main    | ✅         |
| releases prior to 0.1.0 | ❌ |

## Reporting a Vulnerability
- Email `security@modular-accounting.dev` with a detailed report.
- Include reproduction steps, impact assessment, and any proof-of-concept code.
- Expect an acknowledgement within **2 business days**.
- We aim to provide a remediation plan or mitigation within **7 business days**.
- Please do not disclose publicly until a fix is released.

## Coordinated Disclosure
- Security advisories will be published via GitHub Security Advisories.
- Credits may be provided with the reporter’s consent.

## Hardening Checklist
- Rotate API keys and secrets regularly; never commit secrets to the repository.
- Run `pre-commit run --all-files` to ensure secret scanning hooks execute.
- Use environment variables (see `.env.example`) to configure sensitive settings.
- Review [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md) quarterly for updated
  security posture notes and dependency audit status.
- Audit startup failure logs for sensitive payloads; `StartupManager` surfaces
  exception metadata for diagnostics, so ensure startup steps raise errors
  without embedding secrets or personal data.
