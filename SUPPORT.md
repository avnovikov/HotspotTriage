# Support Policy

> **NIST SSDF reference:** RV.2.2 — Address vulnerabilities in delivered software
> *ISO 27001:2022: A.8.8 (Management of technical vulnerabilities), A.8.16 (Monitoring activities)*
> *NIS2 Directive: Art. 21 (Security measures incl. patch management and vulnerability handling)*
> *EU CRA: Art. 13 (Support and end-of-life obligations for products with digital elements)*
> *UK PSTI Act 2022: §11 (No default passwords), §12 (VDP), §13 (Minimum security update period)*
> *COBIT 2019: DSS05.07 (Manage vulnerabilities), MEA03 (Managed compliance and assurance)*
> *SOX: §404 (Internal controls over change management and access)*

HotspotTriage is an open-source developer tool. This document defines the support policy, end-of-life process, and security update commitments applicable to all published releases.

---

## Supported Versions

| Version | Support Status | EOL Date |
|---------|---------------|----------|
| Latest release (`0.1.x`) | ✅ Fully supported — all security and bug fixes | — |
| Previous minor | ⚠️ Security fixes only | 90 days after next minor release |
| Older versions | ❌ Not supported | Passed |

Only the **latest published release** on [GitHub Releases](https://github.com/avnovikov/HotspotTriage/releases) is fully supported at any given time.

---

## Minimum Support Period

Each release of HotspotTriage is supported for a **minimum of 12 months** from its publication date for security fixes.

This satisfies the **UK PSTI Act 2022 §13** minimum support period requirement and aligns with **EU CRA Art. 13** support obligations for products with digital elements.

---

## End-of-Life Process

When a version approaches end-of-life, the following steps are taken **in order**:

1. **30-day advance notice** published in [`CHANGELOG.md`](CHANGELOG.md) and the relevant GitHub Release notes
2. GitHub Release marked as deprecated in the release notes
3. [`README.md`](README.md) updated to indicate EOL status for that version
4. Final security advisory published if any unresolved CVEs exist at EOL date
5. Dependabot alerts reviewed and triaged; critical/high issues addressed before EOL if feasible

This process aligns with:
- **EU CRA Art. 13** — support and EOL obligations for products with digital elements
- **ISO 27001:2022 A.8.8** — management of technical vulnerabilities
- **NIST SSDF RV.2.2** — address vulnerabilities in released software
- **COBIT 2019 DSS05.07** — monitor infrastructure for security events
- **SOX §404** — documented change management and lifecycle controls

---

## Security Fixes

Security vulnerabilities are addressed per the SLA defined in [`docs/SECURITY_REQUIREMENTS.md`](docs/SECURITY_REQUIREMENTS.md) §6.1. To report a vulnerability, see [`SECURITY.md`](SECURITY.md). **Do not open public GitHub issues for security vulnerabilities.**

| Severity | CVSS Score | Response SLA | Fix SLA |
|----------|-----------|-------------|---------|
| Critical | ≥ 9.0 | 24 hours | 7 days |
| High | 7.0 – 8.9 | 48 hours | 14 days |
| Medium | 4.0 – 6.9 | 5 days | 30 days |
| Low | < 4.0 | 30 days | 90 days |

Vulnerability disclosure follows the **CRA Art. 14 / NIS2 Art. 23** timelines:
- Early warning: **24 hours** (actively exploited vulnerabilities only)
- Full notification: **72 hours** of discovery
- Final remediation report: **14 days** after fix release

---

## No Default Passwords

HotspotTriage does not use passwords or authentication credentials in its default configuration. The MCP server and dashboard operate on **localhost only** and do not expose any authentication surface by default.

This satisfies:
- **UK PSTI Act 2022 §11** — no universal default passwords
- **EU CRA Art. 13** — secure default configuration
- **ISO 27001:2022 A.5.17** — authentication information
- **NIST SP 800-53 IA-5** — authenticator management
- **COBIT 2019 DSS05.04** — manage user identities

---

## How to Get Help

| Channel | Purpose |
|---------|---------|
| [GitHub Issues](https://github.com/avnovikov/HotspotTriage/issues/new) | Bug reports and feature requests |
| [GitHub Discussions](https://github.com/avnovikov/HotspotTriage/discussions) | Questions, ideas, and general usage help |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Development setup, branching, PR policy |
| [`SECURITY.md`](SECURITY.md) | Vulnerability reporting and security controls |
| [`docs/SECURITY_REQUIREMENTS.md`](docs/SECURITY_REQUIREMENTS.md) | Detailed security requirements and implementation evidence |

For urgent security issues, email **alexei.128.946@gmail.com** directly (see [`SECURITY.md`](SECURITY.md) for full VDP).

---

## UK PSTI Compliance Statement

This product is developed in alignment with the **UK Product Security and Telecommunications Infrastructure (PSTI) Act 2022**:

| PSTI Section | Requirement | Implementation |
|-------------|-------------|---------------|
| §11 | No universal default passwords | Localhost-only; no credentials in default config |
| §12 | Published vulnerability disclosure policy | See [`SECURITY.md`](SECURITY.md) VDP section |
| §13 | Defined minimum security update period | 12-month minimum support (this document) |

> **Scope note:** HotspotTriage currently operates as a localhost developer tool. PSTI requirements are documented proactively as the product’s network exposure posture may change (see Issue #2).

---

## Regulatory Framework Mapping

| Control | UK PSTI | EU CRA | NIS2 | ISO 27001:2022 | NIST SSDF | NIST SP 800-53 | COBIT 2019 | SOX | SOC 2 |
|---------|---------|--------|------|----------------|-----------|----------------|------------|-----|-------|
| Support period commitment | §13 | Art. 13 | Art. 21 | A.8.8 | RV.2.2 | SI-2 | DSS05.07 | §404 | CC7 |
| EOL process and notice | §13 | Art. 13 | Art. 21 | A.8.8 | RV.2.2 | SI-2 | DSS05.07 | §404 | CC7 |
| No default passwords | §11 | Art. 13 | — | A.5.17 | PW.1.1 | IA-5 | DSS05.04 | — | CC6 |
| Vulnerability disclosure policy | §12 | Art. 14 | Art. 23 | A.6.8 | RV.1.3 | IR-6 | MEA03 | — | CC7 |
| Security fix SLA | §13 | Art. 13 | Art. 21 | A.8.8 | RV.2.2 | SI-2 | DSS05.07 | §404 | CC7 |
| Patch management | §13 | Art. 13 | Art. 21 | A.8.8 | RV.2.2 | SI-2, RA-5 | DSS05.07 | §404 | CC7 |
| Secure default configuration | §11 | Art. 13 | — | A.8.9 | PW.1.1 | CM-6 | DSS05.05 | — | CC6 |
| Post-release monitoring | §13 | Art. 13 | Art. 21 | A.8.16 | RV.2.2 | SI-4 | DSS05.07 | §404 | CC7 |

> **Legend:** — indicates the framework does not have a directly applicable requirement for that control in the context of a local developer tool.

---

## Document Control

| Attribute | Value |
|-----------|-------|
| Created | 2026-05-09 |
| Last reviewed | 2026-05-09 |
| Next review | Annually or on maintainer change |
| Approved by | @avnovikov |
| Related documents | `SECURITY.md`, `CONTRIBUTING.md`, `docs/SECURITY_REQUIREMENTS.md`, `docs/RELEASE_POLICY.md`, `CHANGELOG.md` |
