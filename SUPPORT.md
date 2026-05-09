# Support Policy

> **Regulatory alignment:** UK PSTI Act 2022 §11–13 · EU CRA Art. 13 · NIS2 Art. 21
> ISO 27001:2022 A.8.8 · NIST SP 800-53 SI-2 · COBIT 2019 DSS05 · SOX §404

---

## Supported Versions

| Version | Support Status | EOL Date |
|---------|---------------|----------|
| Latest release | ✅ Fully supported | — |
| Previous minor | ⚠️ Security fixes only | 90 days after next minor release |
| Older versions | ❌ Not supported | — |

---

## Minimum Support Period

Each release of HotspotTriage is supported for a **minimum of 12 months** from its
publication date for security fixes. This satisfies the **UK PSTI Act 2022 §13**
minimum support period requirement and aligns with **EU CRA Article 13** support
and EOL obligations.

---

## End-of-Life Process

1. EOL notice published in `CHANGELOG.md` at least **30 days before** support ends
2. GitHub Release marked as deprecated in the release notes
3. `README.md` updated to indicate EOL status
4. Final security advisory published if any unresolved CVEs exist at EOL

This process aligns with:
- **EU CRA Art. 13** — support and EOL obligations for products with digital elements
- **ISO 27001:2022 A.8.8** — management of technical vulnerabilities
- **NIST SP 800-53 SI-2** — flaw remediation and support lifecycle
- **COBIT 2019 DSS05.07** — monitor infrastructure for security events

---

## Security Fixes

Security vulnerabilities are addressed per the SLA defined in
`docs/SECURITY_REQUIREMENTS.md` §6.1. To report a vulnerability, see [`SECURITY.md`](SECURITY.md).

Vulnerability disclosure follows the **CRA Art. 14 / NIS2 Art. 23** timelines:
- Early warning: **24 hours** (actively exploited only)
- Full notification: **72 hours**
- Final remediation report: **14 days** after fix

---

## No Default Passwords

HotspotTriage does not use passwords or authentication credentials in its default
configuration. The MCP server and dashboard operate on localhost only and do not
expose any authentication surface. This satisfies:
- **UK PSTI Act 2022 §11** — no universal default passwords
- **ISO 27001:2022 A.5.17** — authentication information
- **NIST SP 800-53 IA-5** — authenticator management
- **COBIT 2019 DSS05.04** — manage user identities

---

## UK PSTI Compliance Statement

This product is developed in alignment with the UK Product Security and
Telecommunications Infrastructure (PSTI) Act 2022:

| PSTI Section | Requirement | Implementation |
|---|---|---|
| §11 | No universal default passwords | Localhost-only; no credentials in default config |
| §12 | Published vulnerability disclosure policy | [`SECURITY.md`](SECURITY.md) |
| §13 | Defined minimum security update period | 12-month minimum support; see above |

---

## Getting Help

| Channel | Purpose |
|---------|--------|
| [GitHub Issues](https://github.com/avnovikov/HotspotTriage/issues/new) | Bug reports and feature requests |
| [GitHub Discussions](https://github.com/avnovikov/HotspotTriage/discussions) | Questions, ideas, general usage |
| [`SECURITY.md`](SECURITY.md) | Security vulnerability reports (do not use public issues) |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Development setup, PR workflow, coding standards |

---

## Framework Mapping

| Regulation / Standard | Section | Requirement |
|---|---|---|
| UK PSTI Act 2022 | §11 | No universal default passwords |
| UK PSTI Act 2022 | §12 | Published vulnerability disclosure policy |
| UK PSTI Act 2022 | §13 | Defined minimum security update period |
| EU CRA | Art. 13 | Support and EOL obligations for products with digital elements |
| NIS2 Directive | Art. 21 | Security of network and information systems; incident handling |
| NIS2 Directive | Art. 23 | 72-hour vulnerability notification timeline |
| ISO 27001:2022 | A.8.8 | Management of technical vulnerabilities |
| ISO 27001:2022 | A.5.17 | Authentication information (no default passwords) |
| NIST SP 800-53 | SI-2 | Flaw remediation and support lifecycle |
| NIST SP 800-53 | IA-5 | Authenticator management |
| NIST SSDF | RV.2.2 | Address vulnerabilities in released software |
| COBIT 2019 | DSS05.04 | Manage user identities and access |
| COBIT 2019 | DSS05.07 | Monitor infrastructure and security events |
| SOX | §404 | Internal controls over change management and support lifecycle |
| SOC 2 | CC7 | System monitoring and vulnerability management |

---

## Document Control

| Attribute | Value |
|-----------|-------|
| Created | 2026-05-09 |
| Last reviewed | 2026-05-09 |
| Next review | Annually or on maintainer change |
| Approved by | @avnovikov |
| Related documents | `SECURITY.md`, `CONTRIBUTING.md`, `docs/SECURITY_REQUIREMENTS.md`, `docs/RELEASE_POLICY.md`, `CHANGELOG.md` |
