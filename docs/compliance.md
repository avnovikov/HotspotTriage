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
[![SemVer](https://img.shields.io/badge/SemVer-2.0.0-blue?style=flat)](https://semver.org)
[![Dependabot](https://img.shields.io/badge/Dependabot-enabled-brightgreen?style=flat&logo=dependabot)](https://github.com/avnovikov/HotspotTriage/security/dependabot)

---

## Design Intent — Compliance by Design

HotspotTriage is built as a **local-execution tool with no cloud dependency**, designed from the ground up to operate within regulated and audited software delivery pipelines. Every architectural decision below is a deliberate compliance control, not an afterthought.

### Data Protection & Privacy (GDPR Art. 5)

- **No outbound telemetry.** Repository paths, file contents, and analysis outputs are processed locally only and never transmitted to external systems (§2.1).
- **Username redaction in cache and logs (GDPR Art. 5(1)(c)).** File paths can embed OS usernames, which constitute personal data under GDPR Art. 4(1). HotspotTriage redacts the local username to `first****last` (e.g. `alice` → `a****e`) in on-disk cache files and all application log lines before write. See [#127](https://github.com/avnovikov/HotspotTriage/issues/127).
- **Dashboard is localhost-only.** The FastAPI dashboard binds exclusively to `127.0.0.1` — no paths or metrics are exposed on a routable network interface (§3.2, [#84](https://github.com/avnovikov/HotspotTriage/issues/84)).
- **MCP transport is stdio-only.** No network socket is opened by the MCP server; access is constrained by OS-level process isolation to the authenticated local user (§3.1).

### Supply Chain Integrity (NIS2 Art. 21(2)(d), NIST PW.4.1)

- **Hash-verified dependencies.** All packages are pinned and hash-verified via `uv.lock`; direct `pip install` without the lockfile is not permitted for production installs (§5, §7.1).
- **SBOM on every release** in CycloneDX JSON format, satisfying EU CRA Art. 13 and NTIA minimum elements (§5.3).
- **Dependabot enabled** for continuous post-release CVE monitoring, with mandatory triage SLAs: Critical → 24 h, High → 7 days (§6.1, §6.3).
- **Pre-merge security gates** on every PR: Trivy (CRITICAL/HIGH), CodeQL SAST, and Gitleaks secret scanning — merge is blocked on failure (§6.3).

### Commit & Release Integrity (NIS2 Art. 21(2)(e))

- **SSH-signed commits and tags** — every commit to `main` and every release tag is cryptographically signed. See [CONTRIBUTING.md](../CONTRIBUTING.md#13-ssh-commit-and-tag-signing-required).
- **SemVer 2.0.0** versioning ensures predictable, auditable upgrade paths with no surprise breaking changes.
- **Branch and tag protection** enforced via GitHub rules — no force-push, no unsigned commits, PRs require maintainer approval before merge (§7.3).

### Input Validation & Hardening (NIST SI-10, ISO 27001 A.8.26)

- **Pydantic boundary validation** on all MCP endpoints and dashboard routes: type, length, and format checks before any processing; invalid inputs are rejected with safe, non-leaky error messages (§4, [#84](https://github.com/avnovikov/HotspotTriage/issues/84)).
- **No hardcoded secrets** enforced by Gitleaks on every PR (§7.3).
- **Dashboard binding verified by CodeQL** — the `bind-socket-all-network-interfaces` finding was resolved in [#84](https://github.com/avnovikov/HotspotTriage/issues/84).

---

## Framework Alignment

| Framework | Scope | Control implemented | Reference |
|-----------|-------|--------------------|-----------|
| NIST SP 800-218 (SSDF) | Secure software development practices | Dependency vetting, hash verification, signed releases | [SECURITY_REQUIREMENTS.md §5](SECURITY_REQUIREMENTS.md) |
| NIST SP 800-53 Rev 5 | Security and privacy controls | Input validation (SI-10), access control (AC-3, SC-7), boundary protection | [SECURITY_REQUIREMENTS.md §3–4](SECURITY_REQUIREMENTS.md) |
| ISO/IEC 27001:2022 | Information security management | A.5.34 privacy, A.8.8 vuln mgmt, A.8.20 network security, A.8.26 app security | [SECURITY_REQUIREMENTS.md](SECURITY_REQUIREMENTS.md) |
| COBIT 2019 | IT governance and management | APO10 vendor mgmt, BAI03 solution build, DSS05 security services | [SECURITY_REQUIREMENTS.md](SECURITY_REQUIREMENTS.md) |
| NIS2 Directive (EU 2022/2555) | Risk management, supply chain, incident handling | Art. 21(2)(d) supply chain; Art. 21(2)(e) dev & maintenance; Art. 21(2)(i) network | [SECURITY_REQUIREMENTS.md §1, §5.3](SECURITY_REQUIREMENTS.md) |
| EU Cyber Resilience Act (CRA) | SBOM (Art. 13), vulnerability handling | CycloneDX SBOM on every release, Dependabot + Trivy CVE monitoring | [RELEASE_POLICY.md](RELEASE_POLICY.md) |
| GDPR Art. 5(1)(c) | Data minimisation — username redaction in cache and logs | `first****last` redaction in cache writes and log lines | [#127](https://github.com/avnovikov/HotspotTriage/issues/127) |
| OWASP Top 10 | Secure coding practices | Pydantic input validation, no secrets in code, CodeQL SAST | [CONTRIBUTING.md](../CONTRIBUTING.md) |
| SOC 2 | Operational security controls | No telemetry, localhost-only dashboard, signed commits | [SECURITY.md](../SECURITY.md) |
| SemVer 2.0.0 | Predictable versioning for auditable releases | All releases versioned and tagged per SemVer | [semver.org](https://semver.org) |
| Dependabot | Automated dependency vulnerability management | Continuous CVE alerts; patch PRs auto-raised | [GitHub Security](https://github.com/avnovikov/HotspotTriage/security/dependabot) |

---

## Audit Evidence

Audit artifacts (scan results, SBOM exports, signed release manifests) are stored in [`docs/audit-evidence/`](audit-evidence/).

For questions about compliance posture or to request additional audit documentation, open an issue or see [SUPPORT.md](../SUPPORT.md).
