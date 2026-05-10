# Compliance & Regulatory Posture

HotspotTriage is designed to be part of a **regulated and audited system scope**. This page consolidates all compliance-related signals, framework alignments, and policy references.

> For security vulnerability reporting, see [SECURITY.md](../SECURITY.md).  
> For support policy and EOL process, see [SUPPORT.md](../SUPPORT.md).  
> For full security control requirements, see [docs/SECURITY_REQUIREMENTS.md](SECURITY_REQUIREMENTS.md).

---

## Compliance Badges

[![SOC 2 Compliant](https://img.shields.io/badge/SOC2-Compliant-blue?style=flat&logo=github)](../SECURITY.md)
[![NIST SSDF](https://img.shields.io/badge/NIST%20SSDF-SP%20800--218-blue?style=flat)](SECURITY_REQUIREMENTS.md)
[![NIST SP 800-53](https://img.shields.io/badge/NIST%20SP%20800--53-Rev%205-blue?style=flat)](SECURITY_REQUIREMENTS.md)
[![ISO 27001](https://img.shields.io/badge/ISO%2027001-2022%20Aligned-blue?style=flat)](SECURITY_REQUIREMENTS.md)
[![COBIT 2019](https://img.shields.io/badge/COBIT-2019-blue?style=flat)](SECURITY_REQUIREMENTS.md)
[![EU CRA](https://img.shields.io/badge/EU%20CRA-Art.%2013%20SBOM-003399?style=flat)](RELEASE_POLICY.md)
[![GDPR](https://img.shields.io/badge/GDPR-data%20minimisation-003399?style=flat)](SECURITY_REQUIREMENTS.md)
[![OWASP](https://img.shields.io/badge/OWASP-Top%2010-orange?style=flat)](../CONTRIBUTING.md)
[![CycloneDX SBOM](https://img.shields.io/badge/SBOM-CycloneDX-brightgreen?style=flat)](https://github.com/avnovikov/HotspotTriage/releases)

---

## Design Intent

HotspotTriage is intentionally built to operate within regulated software delivery pipelines. The tool itself processes only local Git history and Python AST metadata — it does not collect, transmit, or store source code or personal data externally.

Key design decisions that support compliance:

- **No outbound telemetry.** All analysis runs locally. No data leaves the developer's machine.
- **Data minimisation (GDPR Art. 5(1)(c)).** Only the metrics necessary for scoring are computed and cached. Raw code is never stored in the cache.
- **SBOM published on every release** in CycloneDX format, supporting EU CRA Art. 13 and NTIA minimum elements.
- **SSH-signed commits and tags** — every release commit is cryptographically signed. See [CONTRIBUTING.md](../CONTRIBUTING.md#13-ssh-commit-and-tag-signing-required).
- **Dependabot enabled** for automated dependency vulnerability tracking.
- **Security scans on every push** via GitHub Actions. See [SECURITY.md](../SECURITY.md) for the vulnerability disclosure policy.

---

## Framework Alignment

| Framework | Scope | Reference |
|-----------|-------|-----------|
| NIST SP 800-218 (SSDF) | Secure software development practices | [SECURITY_REQUIREMENTS.md](SECURITY_REQUIREMENTS.md) |
| NIST SP 800-53 Rev 5 | Security and privacy controls | [SECURITY_REQUIREMENTS.md](SECURITY_REQUIREMENTS.md) |
| ISO/IEC 27001:2022 | Information security management alignment | [SECURITY_REQUIREMENTS.md](SECURITY_REQUIREMENTS.md) |
| COBIT 2019 | IT governance and management | [SECURITY_REQUIREMENTS.md](SECURITY_REQUIREMENTS.md) |
| EU Cyber Resilience Act (CRA) | SBOM (Art. 13), vulnerability handling | [RELEASE_POLICY.md](RELEASE_POLICY.md) |
| GDPR | Data minimisation, no personal data processing | [SECURITY_REQUIREMENTS.md](SECURITY_REQUIREMENTS.md) |
| OWASP Top 10 | Secure coding practices | [CONTRIBUTING.md](../CONTRIBUTING.md) |
| SOC 2 | Operational security controls | [SECURITY.md](../SECURITY.md) |

---

## Audit Evidence

Audit artifacts (scan results, SBOM exports, signed release manifests) are stored in [`docs/audit-evidence/`](audit-evidence/).

For questions about compliance posture or to request additional audit documentation, open an issue or see [SUPPORT.md](../SUPPORT.md).
