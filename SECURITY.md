# Security Policy

> This codebase is built to support SOC 2 controls and is part of the audited system scope.
> It is also developed in alignment with the **EU Cyber Resilience Act (CRA)** and **NIS2 Directive**.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅        |

For the full support and end-of-life policy, see [`SUPPORT.md`](SUPPORT.md).

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

---

## EU Cyber Resilience Act (CRA) Compliance

This project is developed in accordance with **EU Cyber Resilience Act (CRA) Article 13**
security requirements. HotspotTriage is classified as a *product with digital elements*
under the CRA; technical security evidence is documented in
[`docs/SECURITY_REQUIREMENTS.md`](docs/SECURITY_REQUIREMENTS.md).

Key CRA Article 13 controls implemented:

| CRA Requirement | Implementation |
|-----------------|---------------|
| Security by design | NIST SSDF / ISO 27001 aligned SDLC (see `docs/SECURITY_REQUIREMENTS.md`) |
| No known exploitable vulnerabilities at release | `pip-audit` + Trivy mandatory pre-release gate |
| Secure default configuration | Localhost-only dashboard; no default credentials |
| SBOM publicly accessible | CycloneDX JSON attached to every GitHub Release (`sbom.cdx.json`) |
| Vulnerability handling process | See VDP section below |

---

## Vulnerability Disclosure Policy (EU CRA Art. 14 / NIS2 Art. 23)

This VDP satisfies:
- **EU CRA Article 14** — reporting of actively exploited vulnerabilities and security incidents
- **NIS2 Directive Article 23** — 72-hour notification timeline

### Timelines

| Stage | Timeline | Trigger |
|-------|----------|---------|
| Early warning | Within **24 hours** of discovery | Actively exploited vulnerabilities only |
| Full vulnerability notification | Within **72 hours** of discovery | All confirmed vulnerabilities |
| Final remediation report | Within **14 days** of fix being released | All confirmed vulnerabilities |

### Reporting Channels

| Channel | Purpose |
|---------|--------|
| [GitHub Security Advisories](https://github.com/avnovikov/HotspotTriage/security/advisories) | Primary mechanism — private coordinated disclosure and public CVE publication |
| Email: alexei.128.946@gmail.com | Private disclosure for reporters who prefer email |
| [ENISA](https://www.enisa.europa.eu/) | EU-level reporting for actively exploited vulnerabilities |
| National CSIRT (PT): [CNCS](https://www.cncs.gov.pt/) | National CSIRT notification channel |

> **Note for solo OSS maintainers:** GitHub Security Advisories serve as the primary
> CRA-compliant reporting mechanism. ENISA and CNCS notification applies only to
> actively exploited vulnerabilities (CRA Art. 14(2)) and is coordinated via
> GitHub Security Advisories where a CVE is issued.

### Process

1. Reporter submits via GitHub Security Advisory or email
2. Maintainer acknowledges within **48 hours**
3. Severity assessed using CVSS v3.1 (see `docs/SECURITY_REQUIREMENTS.md` §6.1 for SLA table)
4. Early warning issued to ENISA/CSIRT within **24 hours** if actively exploited
5. Full notification published within **72 hours** of confirmation
6. Fix developed, tested, and released per `docs/RELEASE_POLICY.md` hotfix process
7. Final remediation report published within **14 days** of fix release
