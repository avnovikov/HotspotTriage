# Release Policy

> **Document owner:** Repository maintainer (`@avnovikov`)
> **Review cadence:** At each release milestone, or upon any significant change to the release toolchain
> **Applicable frameworks:** NIST SP 800-218 (SSDF), NIST SP 800-53 Rev 5, ISO/IEC 27001:2022, COBIT 2019
> **Status:** Active
> **Relates to:** [Issue #105](https://github.com/avnovikov/HotspotTriage/issues/105)

---

## 1. Purpose and Scope

This document defines the release policy for **HotspotTriage**, covering versioning conventions, pre-release quality and security gates, the release process including artefact signing and publication, supported version lifecycle, and the emergency hotfix process.

It satisfies the following NIST Secure Software Development Framework (SSDF) SP 800-218 practices:

| Practice | Description |
|----------|-------------|
| **PS.3.1** | Archive each release and protect it from tampering |
| **PW.8.2** | Ensure that all security findings are addressed prior to public release |

These requirements align with ISO/IEC 27001:2022 Annex A controls and COBIT 2019 governance objectives as noted throughout.

---

## 2. Versioning

> *NIST SSDF PS.3.1 — each released version must be uniquely identifiable and reproducible*
> *ISO 27001:2022 reference: A.8.32 (Change management)*
> *COBIT 2019 reference: BAI06 (Manage IT Changes)*

HotspotTriage follows **Semantic Versioning 2.0.0** ([semver.org](https://semver.org)): `MAJOR.MINOR.PATCH`.

| Component | Increment when |
|-----------|---------------|
| `MAJOR` | Breaking change to MCP API, CLI interface, or output schema |
| `MINOR` | New feature or capability, backward-compatible |
| `PATCH` | Bug fix, dependency update, documentation-only change, security patch |

### Pre-release naming

| Type | Convention | Example |
|------|------------|---------|
| Release candidate | `vX.Y.Z-rc.N` | `v1.1.0-rc.1` |
| Beta | `vX.Y.Z-beta.N` | `v1.1.0-beta.1` |

Pre-release versions are not considered stable and do not receive security backports.

### Version source of truth

The canonical version is defined in `pyproject.toml` under `[project] version`. This must be updated as part of every release PR.

---

## 3. Pre-Release Gate

> *NIST SSDF PW.8.2 — verify that security findings identified during testing have been addressed before releasing the software*
> *ISO 27001:2022 reference: A.8.8 (Management of technical vulnerabilities), A.8.29 (Security testing in development and acceptance)*
> *COBIT 2019 reference: BAI07 (Manage IT Change Acceptance and Transitioning)*

All items in the following checklist must be satisfied before a release tag is created. This gate applies to both regular and hotfix releases unless explicitly noted in Section 6.

### 3.1 Full Pre-Release Checklist

**Tests & Quality**
- [ ] All `pytest` tests pass in CI (`tests.yml` workflow green)
- [ ] `pylint` score ≥ **9.0** across `src/hotspottriage/`: `uv run pylint src/hotspottriage --fail-under=9.0`
- [ ] No new `pylint` Error (E) or Fatal (F) findings introduced relative to previous release

> *Note: A `[tool.pylint.main]` `fail-under = 9.0` entry should be added to `pyproject.toml` to enforce this threshold programmatically.*

**Security**
- [ ] `pip-audit` run locally with clean output (no Critical or High CVEs in direct or transitive dependencies):
  ```bash
  uv export --format requirements-txt | pip-audit -r /dev/stdin
  ```
- [ ] CI security workflow (`security.yml`) passing: CodeQL, Trivy (CRITICAL/HIGH), Gitleaks
- [ ] No open Critical or High Dependabot alerts on the release branch
- [ ] Dependency vetting checklist completed per `docs/SECURITY_REQUIREMENTS.md` §5.1

**Release Artefacts**
- [ ] Version bumped in `pyproject.toml`
- [ ] `CHANGELOG.md` updated: `[Unreleased]` section promoted to `[vX.Y.Z] — YYYY-MM-DD`
- [ ] SBOM generated (see [Issue #107](https://github.com/avnovikov/HotspotTriage/issues/107)): `uv run cyclonedx-py environment --of JSON -o sbom.cdx.json`
- [ ] Wheel and sdist built cleanly: `uv build` (produces `dist/hotspottriage-X.Y.Z-*.whl` and `dist/hotspottriage-X.Y.Z.tar.gz`)

**Governance**
- [ ] PR reviewed and approved by at least one maintainer
- [ ] All checklist items above documented in the release PR body

---

## 4. Release Process

> *NIST SSDF PS.3.1 — archive and protect each release version of the software and its associated data*
> *ISO 27001:2022 reference: A.8.32 (Change management), A.5.33 (Protection of records)*
> *COBIT 2019 reference: BAI07 (Manage IT Change Acceptance and Transitioning)*
> *NIST SP 800-53 reference: SA-12 (Supply Chain Protection), CM-3 (Configuration Change Control)*

### 4.1 SSH Commit and Tag Signing

HotspotTriage enforces a **two-layer SSH signing policy** that establishes an unbroken chain of custody from individual commit to published release:

- **All commits merged to `main` must be SSH-signed.** This is enforced via the *"Require signed commits"* branch protection rule on `main`.
- **All release tags must be SSH-signed.** Unsigned tags must not be used for releases.

This provides cryptographic proof of authorship for every change and every release, satisfying NIST SSDF PS.3.1 (release integrity), ISO 27001:2022 A.8.32 (change management), and NIST SP 800-53 SA-12 (supply chain protection).

> **SSH signing setup is documented in `CONTRIBUTING.md` §1.3.** All contributors and maintainers must complete that one-time workstation configuration before committing.

**GitHub requirement:** The SSH key must be registered under **Settings → SSH and GPG keys** as a *Signing Key* (distinct from the authentication key entry). GitHub will then display the `Verified` badge on signed commits and tags, which serves as audit evidence.

### 4.2 Step-by-Step Release Process

1. **Prepare release branch**
   ```bash
   git checkout -b release/vX.Y.Z
   ```

2. **Complete pre-release gate** — all items in Section 3.1 must be checked.

3. **Bump version** in `pyproject.toml`:
   ```toml
   version = "X.Y.Z"
   ```

4. **Update `CHANGELOG.md`** — promote `[Unreleased]` to `[vX.Y.Z] — YYYY-MM-DD`, add new empty `[Unreleased]` section at top.

5. **Build artefacts**:
   ```bash
   uv build
   # Produces: dist/hotspottriage-X.Y.Z-py3-none-any.whl
   #           dist/hotspottriage-X.Y.Z.tar.gz
   ```

6. **Generate SBOM** (ref [Issue #107](https://github.com/avnovikov/HotspotTriage/issues/107)):
   ```bash
   uv run cyclonedx-py environment --of JSON -o sbom.cdx.json
   ```

7. **Open and merge release PR** — must have at least one approval.

8. **Create SSH-signed tag** on `main` after merge:
   ```bash
   git checkout main && git pull
   git tag -s vX.Y.Z -m "Release vX.Y.Z"
   git push origin vX.Y.Z
   ```

9. **Publish GitHub Release** — create via GitHub UI or CLI:
   - Title: `vX.Y.Z`
   - Body: copy from `CHANGELOG.md` for this version
   - Attach: `dist/hotspottriage-X.Y.Z-*.whl`, `dist/hotspottriage-X.Y.Z.tar.gz`, `sbom.cdx.json`

10. **Verify** — confirm the tag shows `Verified` on GitHub (SSH signing confirmed).

### 4.3 Tag Protection

Release tags (`v*`) must be protected:
- No force-push to release tags
- No deletion of release tags
- Enforced via GitHub repository **tag protection rules** (Settings → Rules → Tag protection)

---

## 5. Supported Versions

> *ISO 27001:2022 reference: A.8.8 (Management of technical vulnerabilities)*
> *NIST SP 800-53 reference: SI-2 (Flaw Remediation)*

Only the **latest release** receives security fixes and backports. Prior versions are unsupported.

| Version | Support status |
|---------|---------------|
| Latest (`vX.Y.Z`) | ✅ Active — security fixes and patches applied |
| Previous minor/major | ❌ Unsupported — upgrade to latest recommended |
| Pre-release (`rc`, `beta`) | ❌ Unsupported — for evaluation only |

Users on unsupported versions are encouraged to upgrade. The vulnerability disclosure and reporting process is defined in `SECURITY.md`.

---

## 6. Hotfix / Emergency Release Process

> *NIST SSDF RV.2.2 — address vulnerabilities; PS.3.1 — protect the release*
> *ISO 27001:2022 reference: A.8.8 (Management of technical vulnerabilities), A.8.32 (Change management)*
> *COBIT 2019 reference: DSS02 (Manage Service Requests and Incidents), BAI07*
> *NIST SP 800-53 reference: IR-4 (Incident Handling), SI-2 (Flaw Remediation)*

### 6.1 Trigger Criteria

A hotfix release is warranted when any of the following conditions are met:

- A **Critical or High CVE** is confirmed in a direct or transitive dependency (per severity classifications in `docs/SECURITY_REQUIREMENTS.md` §6.1)
- A **security regression** is introduced by a merged PR and confirmed exploitable
- An **exploitable vulnerability** is reported and validated via responsible disclosure (`SECURITY.md`)
- A **Critical runtime defect** causes data corruption or complete loss of service for all users

### 6.2 Fast-Track Checklist

The following is the mandatory subset of the full pre-release gate (Section 3.1) that applies to hotfix releases. Items marked *(deferred)* must be completed within **24 hours post-release**.

**Must complete before tagging:**
- [ ] Fix developed on a dedicated `hotfix/vX.Y.Z` branch — no unrelated changes
- [ ] `pytest` full suite passes in CI
- [ ] `pip-audit` clean on the hotfix branch (targeted at the fixed dependency)
- [ ] CI security workflow (`security.yml`) passing: CodeQL, Trivy, Gitleaks
- [ ] Version bumped to next `PATCH` (or `MINOR` if the fix introduces a breaking mitigation)
- [ ] `CHANGELOG.md` updated with at minimum: version, date, and one-line CVE/issue summary
- [ ] PR reviewed — a second maintainer review is strongly preferred; **self-review is permitted only when no second maintainer is reachable within the SLA window**, and must be explicitly documented in the PR body with rationale
- [ ] Release tag SSH-signed — **commit and tag signing is mandatory and non-negotiable, even in a hotfix**. SSH signing adds seconds, not hours, and must never be skipped under time pressure

**Deferred (complete within 24h post-release):**
- [ ] `CHANGELOG.md` expanded with full description of the vulnerability and fix
- [ ] Dependency vetting table in `docs/SECURITY_REQUIREMENTS.md` §5.2 updated if a dependency was changed
- [ ] GitHub Security Advisory published
- [ ] `pylint` full review (score ≥ 9.0 check) — *(deferred to next regular release if fix is surgical)*
- [ ] SBOM regenerated and attached to GitHub Release

### 6.3 SLA Alignment

Hotfix release SLAs are defined in `docs/SECURITY_REQUIREMENTS.md` §6.1:

| Severity | Release SLA |
|----------|-------------|
| Critical (CVSS 9.0–10.0) | 24 hours from confirmation |
| High (CVSS 7.0–8.9) | 7 calendar days |

---

## 7. Document Control

| Attribute | Value |
|-----------|-------|
| Created | 2026-05-09 |
| Last reviewed | 2026-05-09 |
| Next review | At next release milestone |
| Approved by | @avnovikov |
| Related documents | `SECURITY.md`, `CHANGELOG.md`, `docs/SECURITY_REQUIREMENTS.md`, `CONTRIBUTING.md`, SBOM workflow (issue #107) |
