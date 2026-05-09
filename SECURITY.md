# Security Policy

> This codebase is built to support SOC 2 controls and is part of the audited system scope.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅        |

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Instead, report them privately:
- **Email**: alexei.128.946@gmail.com
- **Response time**: Within 48 hours
- **Disclosure**: Coordinated disclosure after patch is released

## Security Controls

This repository implements the following SOC 2 Trust Services Criteria:

| Control | Implementation |
|---------|---------------|
| CC6 – Logical Access | Branch protection, CODEOWNERS, MFA required |
| CC7 – Monitoring | CodeQL, Trivy, Gitleaks scans on every PR |
| CC8 – Change Management | Required PR reviews, status checks before merge |

## Security Scanning

All pull requests are automatically scanned for:
- **SAST** via CodeQL (static analysis)
- **Dependency vulnerabilities** via Trivy + Dependabot
- **Secret leakage** via Gitleaks

**Dependabot:** Pull requests for dependency updates run on the schedule in [`.github/dependabot.yml`](.github/dependabot.yml); reviewers triage and merge them when required checks pass, prioritizing security-related changes.

Results are visible in the [Security tab](https://github.com/avnovikov/HotspotTriage/security).
