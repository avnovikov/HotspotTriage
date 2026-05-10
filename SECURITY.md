# Security Policy

> **Document owner:** Repository maintainer (`@avnovikov`)
> **Review cadence:** At each release milestone, or upon any significant architectural change
> **Status:** Active
> **Detailed control requirements, framework mapping, and implementation evidence:** [`docs/SECURITY_REQUIREMENTS.md`](docs/SECURITY_REQUIREMENTS.md)

## 1. Purpose and Scope

This document defines the security policy for **HotspotTriage**.

HotspotTriage is a local-execution developer tool that provides code quality analysis and hotspot triage through an MCP server and an optional local dashboard. This policy describes how security vulnerabilities are reported, assessed, remediated, and disclosed. It also states the project's high-level security commitments.

This document is the public-facing policy layer. Detailed control statements, framework mappings, and audit-oriented implementation evidence are maintained in [`docs/SECURITY_REQUIREMENTS.md`](docs/SECURITY_REQUIREMENTS.md).

## 2. Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x | Yes |

For the full support and end-of-life policy, see [`SUPPORT.md`](SUPPORT.md).

## 3. Reporting a Vulnerability

Please **do not** open public GitHub issues for suspected security vulnerabilities.

Report vulnerabilities through one of the following private channels:

- **GitHub Security Advisories:** [Private advisory reporting](https://github.com/avnovikov/HotspotTriage/security/advisories)
- **Email:** `alexei.128.946@gmail.com`

When reporting a vulnerability, include:

- A clear description of the issue
- The affected version or commit, if known
- Reproduction steps or proof of concept, if available
- Any impact assessment you believe is relevant

The maintainer aims to acknowledge receipt within **48 hours**.

## 4. Vulnerability Handling and Disclosure

Reported vulnerabilities are handled under a coordinated disclosure process.

The project applies the following policy:

- Reports are assessed privately before public disclosure.
- Severity is classified using **CVSS v3.1** and the project's documented remediation process.
- Valid vulnerabilities are remediated according to the severity-based handling process defined in [`docs/SECURITY_REQUIREMENTS.md`](docs/SECURITY_REQUIREMENTS.md).
- Public disclosure occurs after a fix, mitigation, or other appropriate response is available.
- Where legal or regulatory reporting obligations apply, notifications are handled by the maintainer as part of the incident response process.

For detailed remediation SLAs, monitoring activities, and framework-aligned vulnerability handling requirements, see Section 6 of [`docs/SECURITY_REQUIREMENTS.md`](docs/SECURITY_REQUIREMENTS.md).

## 5. Security Policy Statements

HotspotTriage is maintained under the following security policy commitments:

- **Private vulnerability intake:** Security issues must be reported privately and handled through coordinated disclosure.
- **Local-first architecture:** The MCP server uses stdio transport, and the optional dashboard is intended for local use only.
- **Protected change management:** Changes to protected branches and releases are governed through pull requests, reviews, signed commits or tags where required, and repository protections.
- **Security scanning:** Pull requests and protected branches are subject to automated security checks, including static analysis, dependency scanning, and secret scanning.
- **Dependency control:** Third-party components are reviewed, version-controlled, and subject to vulnerability monitoring.
- **Evidence-backed requirements:** Detailed security requirements and control mappings are maintained separately so the policy remains stable while evidence and implementation detail can evolve.

## 6. Regulatory and Framework Alignment

HotspotTriage is developed with reference to security and software assurance frameworks that may be relevant to audit, governance, or product compliance activities, including:

- NIST SP 800-218 (SSDF)
- NIST SP 800-53 Rev. 5
- ISO/IEC 27001:2022
- COBIT 2019
- NIS2 Directive
- EU Cyber Resilience Act, where applicable to the product context

Framework-specific mappings and the detailed control inventory are maintained in [`docs/SECURITY_REQUIREMENTS.md`](docs/SECURITY_REQUIREMENTS.md), not in this policy.

## 7. Related Documents

- [`docs/SECURITY_REQUIREMENTS.md`](docs/SECURITY_REQUIREMENTS.md) - detailed security requirements, control inventory, framework mapping, and implementation references
- [`docs/RELEASE_POLICY.md`](docs/RELEASE_POLICY.md) - release and hotfix process
- [`SUPPORT.md`](SUPPORT.md) - supported versions and end-of-life policy
- [`CONTRIBUTING.md`](CONTRIBUTING.md) - contribution and development workflow requirements
