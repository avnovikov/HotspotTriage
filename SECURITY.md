# Security Policy

> This codebase is built to support SOC 2 controls and is part of the audited system scope.
> It is also developed in alignment with the **EU Cyber Resilience Act (CRA)**, **NIS2 Directive**, and **UK PSTI Act 2022**.

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

---

## Regulatory Cross-Reference Mapping

The table below maps every security control implemented in HotspotTriage to all applicable
regulatory and framework references simultaneously. Detailed requirements and implementation
evidence are in [`docs/SECURITY_REQUIREMENTS.md`](docs/SECURITY_REQUIREMENTS.md).

| Control | SOC 2 | NIST SSDF (SP 800-218) | NIST SP 800-53 | ISO 27001:2022 | COBIT 2019 | EU CRA | NIS2 | UK Cyber Essentials | UK PSTI | SOX |
|---------|-------|------------------------|----------------|----------------|------------|--------|------|---------------------|---------|-----|
| Security requirements documented | CC7 | PW.1.1 | PL-8 | A.5.1 | APO02 | Art. 13 | Art. 21 | — | — | — |
| CIA objectives defined | CC6, CC7 | PW.1.1 | SC-8, SI-12 | A.5.1 | BAI03 | Art. 13 | Art. 21 | — | — | — |
| Localhost-only binding (no network exposure) | CC6 | PW.1.1 | SC-7, AC-17 | A.8.20 | DSS05 | Art. 13 | Art. 21 | Firewalls | — | — |
| No default passwords / credentials | CC6 | PW.1.1 | IA-5 | A.5.17 | DSS05.04 | Art. 13 | — | Access Control | §11 | — |
| Input validation (Pydantic, path checks) | CC7 | PW.1.1 | SI-10 | A.8.26 | BAI03 | Art. 13 | — | — | — | — |
| Dependency pinning (`uv.lock`, hash verify) | CC7 | PW.4.1 | SR-3 | A.5.19 | APO10 | Art. 13 | Art. 21(d) | Patch Management | — | — |
| Dependency vetting table | CC7 | PW.4.1 | SR-3 | A.5.20, A.5.22 | APO10 | Art. 13 | Art. 21(d) | — | — | — |
| `pip-audit` pre-release gate | CC7 | PW.4.1 | SR-3, SI-2 | A.8.8 | DSS05.07 | Art. 13 | Art. 21 | Patch Management | — | §404 |
| SBOM (CycloneDX JSON, publicly accessible) | CC7 | PS.2.1 | SR-4 | A.5.19 | APO10 | Art. 13 | Art. 21(d) | — | — | — |
| SSH-signed commits | CC8 | PS.1.1 | CM-3, SA-12 | A.8.32 | BAI07 | Art. 13 | — | — | — | §404 |
| SSH-signed release tags | CC8 | PS.3.1 | CM-3 | A.8.32 | BAI07 | Art. 13 | — | — | — | §404 |
| Branch protection / PR-only merges to `main` | CC8 | PO.1.1 | CM-3, AC-3 | A.8.32 | BAI07 | Art. 13 | — | Access Control | — | §404 |
| Access control policy (merge and release rights) | CC6 | PO.1.1 | AC-2, AC-3 | A.5.15, A.5.18 | DSS05.04 | Art. 13 | — | Access Control | — | §404 |
| SAST (CodeQL) | CC7 | PW.7.2 | RA-5, SI-10 | A.8.28 | DSS05.07 | Art. 13 | — | — | — | — |
| Secret scanning (Gitleaks) | CC7 | PW.7.2 | RA-5 | A.8.12 | DSS05 | Art. 13 | — | — | — | — |
| Dependency scanning (Trivy, Dependabot) | CC7 | RV.2.2 | RA-5, SI-2 | A.8.8, A.8.16 | DSS05.07 | Art. 13 | Art. 21 | Patch Management | — | — |
| CVSS-based severity classification and SLA | CC7 | RV.2.2 | RA-5, SI-2 | A.8.8 | MEA03 | Art. 14 | Art. 23 | — | — | — |
| Vulnerability disclosure policy (24h / 72h / 14d) | CC7 | RV.1.3 | IR-6 | A.6.8 | MEA03 | Art. 14 | Art. 23 | — | §12 | — |
| ENISA / CSIRT notification channel | — | — | IR-6 | A.6.8 | MEA03 | Art. 14 | Art. 23 | — | — | — |
| Release policy (changelog, signed artefacts) | CC8 | PS.3.1 | CM-3 | A.8.32 | BAI07 | Art. 13 | — | — | — | §404 |
| Secure SDLC / contributing policy | CC8 | PO.1.1 | SA-15 | A.8.25 | BAI03 | Art. 13 | Art. 21 | Secure Configuration | — | — |
| Test data statement (synthetic fixtures only) | CC7 | — | SA-15 | A.8.33 | BAI03 | — | — | — | — | — |
| Configuration baseline (`uv.lock`, `pyproject.toml`) | CC8 | — | CM-2, CM-3 | A.8.9 | BAI10 | Art. 13 | — | Secure Configuration | — | §404 |
| Post-release monitoring SLA (Dependabot, Trivy cron) | CC7 | RV.2.2 | SI-4, SI-2 | A.8.16 | DSS05.07 | Art. 13 | Art. 21 | — | — | — |
| Supply chain security statement | CC7 | PW.4.1 | SR-3 | A.5.19–5.22 | APO10 | Art. 13 | Art. 21(d) | — | — | — |
| GDPR data minimisation (file path handling) | — | — | — | A.5.34 | MEA03 | — | — | — | — | — |
| End-of-life / support period policy | CC7 | RV.2.2 | SI-2 | A.8.8 | DSS05.07 | Art. 13 | Art. 21 | — | §13 | §404 |
| Support channel and getting-help documentation | — | PO.1.1 | — | A.6.8 | DSS05 | Art. 13 | — | — | §12 | — |

> **Legend:** Controls marked — indicate the framework does not have a directly applicable requirement
> for that control in the context of a local developer tool. Detailed evidence and implementation
> notes for each control are in [`docs/SECURITY_REQUIREMENTS.md`](docs/SECURITY_REQUIREMENTS.md).
