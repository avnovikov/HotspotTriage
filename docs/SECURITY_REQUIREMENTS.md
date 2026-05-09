# Security Requirements

> **Document owner:** Repository maintainer (`@avnovikov`)
> **Review cadence:** At each release milestone, or upon any significant architectural change
> **Applicable frameworks:** NIST SP 800-218 (SSDF), NIST SP 800-53 Rev 5, ISO/IEC 27001:2022, COBIT 2019
> **Status:** Active
> **Relates to:** [Issue #104](https://github.com/avnovikov/HotspotTriage/issues/104), [Issue #127](https://github.com/avnovikov/HotspotTriage/issues/127)

---

## 1. Purpose and Scope

This document establishes the security requirements for **HotspotTriage**, a local-execution developer tool that provides code quality analysis and hotspot triage via an MCP (Model Context Protocol) server and a companion dashboard.

It satisfies the following NIST Secure Software Development Framework (SSDF) SP 800-218 practices:

| Practice | Description |
|----------|-------------|
| **PW.1.1** | Document security requirements prior to and during software design |
| **PW.4.1** | Acquire and maintain well-secured software components (supply chain vetting) |
| **RV.2.2** | Analyse vulnerabilities and prioritise remediation |

These requirements align with ISO/IEC 27001:2022 Annex A controls and COBIT 2019 governance objectives as noted throughout.

---

## 2. Security Objectives (CIA) — NIST PW.1.1

> *ISO 27001:2022 reference: A.5.1 (Information security policies), A.8.6 (Capacity management)*
> *COBIT 2019 reference: APO02 (Strategy), BAI03 (Solution Identification and Build)*

### 2.1 Confidentiality

HotspotTriage analyses local repository paths provided by the developer. The following confidentiality requirements apply:

- Repository paths, file contents, and analysis outputs are processed **locally only** and are never transmitted to external systems.
- Analysis artefacts (cached results) are stored on the local filesystem under the developer's user account and are protected by OS-level access controls.
- No telemetry, usage data, or repository metadata is collected or externalised.

### 2.2 Integrity

Triage scores and analysis outputs must accurately reflect the state of the analysed codebase, given the normalisation parameters in effect at the time of analysis.

**User-configurable parameters:** Normalisation weights and scoring parameters are intentionally configurable by the authenticated local user at runtime (e.g., via the dashboard UI, per [Issue #56](https://github.com/avnovikov/HotspotTriage/issues/56)). This is a designed capability, not a control gap. The integrity requirement applies to the **computation logic itself** — given a fixed set of inputs and parameters, the output must be deterministic, reproducible, and free from unauthorised manipulation.

The following integrity controls apply:

- **Computation integrity:** Core analysis and scoring logic must not be alterable at runtime by any mechanism other than the documented user-configurable parameters.
- **Parameter integrity:** User-supplied normalisation parameters are validated at input boundaries (type, range, and format checks) before being applied to scoring computations. Invalid or out-of-range values are rejected with safe error messages (see Section 4).
- **Audit transparency:** Changes to normalisation parameters are reflected immediately in analysis output. Users are expected to understand that different parameter configurations will produce different triage rankings — this is expected and documented behaviour, not an integrity violation.
- **Input integrity:** All inputs to analysis functions are validated at trust boundaries prior to processing (see Section 4).
- **Dependency integrity:** Dependency integrity is enforced via hash verification in `uv.lock` (see Section 5).

> *This integrity model is consistent with ISO 27001:2022 A.8.26 (application security requirements) and NIST SP 800-53 SI-10 (Information Input Validation), acknowledging that user-driven parameterisation is an authorised and documented feature of the system.*

### 2.3 Availability

HotspotTriage is a **local-execution developer tool**. Availability is defined as the ability of the developer to invoke the tool on demand on their workstation. No uptime SLA applies.

Continuity is ensured by:
- Version-controlled source code available via GitHub.
- Fully reproducible dependency installation via `uv sync`.
- No external runtime dependencies (no cloud services, no remote APIs).

> *This proportionate availability treatment is consistent with ISO 27001:2022 A.8.6 (capacity management) and COBIT DSS04 (continuity management), calibrated to the asset classification of a local developer tool.*

### 2.4 Personal data and data minimisation (GDPR alignment)

> *ISO 27001:2022 reference: A.5.34 (Privacy and protection of personally identifiable information)*
> *GDPR reference: Art. 4(1) (personal data), Art. 5(1)(c) (data minimisation), Art. 6(1)(b) (contract / tool use)*

HotspotTriage does not process personal data as its primary function. However, file system paths supplied as input may constitute personal data under GDPR Article 4(1) when they contain an operating-system username or similar identifier (for example paths under ``/home/<user>/`` or ``/Users/<user>/``).

**Personal data scope (documentation)** — Same scope as [Issue #127](https://github.com/avnovikov/HotspotTriage/issues/127): paths are not the product’s purpose, but may embed identifiers.

**Outputs and surfaces (risk register)**

- **CLI:** Table, JSON, and CSV output print paths to stdout/stderr for the session. HotspotTriage does not persist that stream or send it to telemetry; any retention is solely from the user’s shell, scripts, or CI log capture.
- **Dashboard HTTP API** (e.g. stats, heatmap, cache context): JSON or SSE payloads may include paths. The dashboard binds to ``127.0.0.1`` only, so this process does not expose those responses on a routable interface. For cache context and config snapshots, the API adds ``*_display`` string fields with the same username redaction as logs; the UI binds visible repo fields to those while retaining canonical paths for requests.
- **MCP:** Tool responses may include paths for the requesting client’s immediate use. Persisting or forwarding those payloads is the **consuming system’s** responsibility.
- **On-disk cache:** Block cache pickle rows use **username redaction** on string leaves before write: the detected local username becomes ``<first>****<last>`` (single-character names: ``<char>****``), so the full username substring is not stored in cache files.
- **Application logs:** The MCP-attached dashboard log buffer and ``hotspottriage.path_utils.sanitize_log_value`` apply the same username redaction to formatted lines and sanitised path fragments.
- **External systems:** No analytics, telemetry, or crash reporting sends file paths outside the machine from HotspotTriage itself.

**Lawful basis (documentation only, not legal advice).** Processing is described here as necessary for providing the analysis functionality requested by the local user (**GDPR Article 6(1)(b)** — performance of the “contract” with the end user in the sense used in [Issue #127](https://github.com/avnovikov/HotspotTriage/issues/127)).

---

## 3. Transport and Access Control — NIST PW.1.1

> *ISO 27001:2022 reference: A.8.2 (Privileged access rights), A.8.20 (Networks security)*
> *COBIT 2019 reference: DSS05.04 (Manage user access)*
> *NIST SP 800-53 reference: AC-3 (Access Enforcement), AC-17 (Remote Access)*

### 3.1 MCP Server Transport

The MCP server communicates exclusively via the **stdio transport** (local inter-process pipe between `stdin` and `stdout`). This means:

- **No network socket is opened** by the MCP server process.
- Communication is limited to the process that spawns the server (e.g., Claude Desktop, VS Code MCP extension), which runs under the same authenticated local OS user account.
- Access is implicitly restricted by **OS-level process isolation** — no process belonging to a different user or remote host can communicate with the MCP server.
- No authentication token, API key, or session credential is required or appropriate for this deployment model.

> *This architecture provides access control equivalent to NIST SP 800-53 AC-3 (Access Enforcement) through OS process isolation, consistent with the principle of least privilege (ISO 27001:2022 A.8.2).*

### 3.2 Dashboard (HTTP Interface)

The optional companion dashboard (FastAPI/uvicorn) is subject to the following constraint:

- The dashboard **binds exclusively to `127.0.0.1`** (localhost). No external network interfaces are exposed.
- This control was implemented and verified as part of [Issue #84](https://github.com/avnovikov/HotspotTriage/issues/84) (CodeQL finding `bind-socket-all-network-interfaces` resolved).
- Access is restricted to processes and users on the local machine, consistent with OS-level network namespace isolation.

> *This satisfies ISO 27001:2022 A.8.20 (network security) and NIST SP 800-53 SC-7 (Boundary Protection) in the context of a local developer tool.*

### 3.3 Authentication Statement

No user authentication mechanism is implemented for either the MCP server or the dashboard. This is a deliberate and documented architectural decision based on the following rationale:

- Both interfaces are accessible only to the authenticated local OS user.
- The operating system's login authentication serves as the access control boundary.
- Implementing additional authentication would introduce complexity without a proportionate security benefit for a local tool.

This decision shall be **re-evaluated** if HotspotTriage is ever extended to support multi-user environments, remote access, or network-exposed endpoints.

---

## 4. Input Validation and Output Sanitisation — NIST PW.1.1

> *ISO 27001:2022 reference: A.8.26 (Application security requirements)*
> *COBIT 2019 reference: BAI03 (Solution Identification and Build)*
> *NIST SP 800-53 reference: SI-10 (Information Input Validation)*

### 4.1 Requirements

All user-supplied or externally-sourced inputs to MCP endpoints and dashboard routes must be:

- Validated at trust boundaries using schema-based validation (Pydantic models).
- Checked for explicit type, length, and format constraints prior to processing.
- Rejected with safe, non-leaky error messages if constraints are violated.
- Sanitised before inclusion in log output to prevent log injection.

Local filesystem paths must be resolved through a centralised path resolution utility and constrained to permitted directories.

### 4.2 Implementation Evidence

The following issues document the implementation of these requirements:

| Issue | Status | Scope |
|-------|--------|-------|
| [#84 — Add Pydantic boundary validation and strict input size limits](https://github.com/avnovikov/HotspotTriage/issues/84) | ✅ Closed | Pydantic models, path injection (CodeQL), log sanitisation |
| [#83 — Harden input handling against injection and overflow risks](https://github.com/avnovikov/HotspotTriage/issues/83) | 🔄 Open | Centralised input filtering layer, allowlists, resource exhaustion |

> *These requirements are stated here per NIST PW.1.1. Implementation detail is tracked in the referenced issues.*

---

## 5. Supply Chain and Component Vetting — NIST PW.4.1

> *ISO 27001:2022 reference: A.5.19 (Information security in supplier relationships), A.5.20 (Addressing security within supplier agreements), A.5.22 (Monitoring and review of supplier services)*
> *COBIT 2019 reference: APO10 (Vendor Management)*
> *NIST SP 800-53 reference: SR-3 (Supply Chain Controls and Processes)*

### 5.1 Vetting Policy

All third-party dependencies must be vetted prior to adoption and re-vetted at each **release milestone** or upon introduction of a new direct dependency. Evidence of vetting is captured in the release PR description and retained in version history.

**Vetting criteria (all must be satisfied):**

- [ ] Sourced from PyPI with hash verification via `uv.lock`
- [ ] No known critical CVEs at time of adoption (verified via [OSV Database](https://osv.dev) and PyPI Advisory DB)
- [ ] Actively maintained — commit activity within the preceding 12 months
- [ ] Licence compatible with project licence: MIT, Apache 2.0, or BSD variants permitted; GPL-family flagged for legal review
- [ ] Transitive dependencies reviewed for anomalies (unexpected network access, unusual permissions)

### 5.2 Current Dependency Vetting Evidence

The following table documents vetting evidence for all current direct dependencies at the time of this document's creation:

| Package | Version Constraint | Source | Vetting Notes |
|---------|--------------------|--------|---------------|
| `deepcsim` | `>=0.1.2,<0.2` | PyPI | Small package; pinned minor range; hash-verified in `uv.lock` |
| `radon` | `>=6.0` | PyPI | Established code metrics library; widely used; actively maintained |
| `pylint` | `>=3.0` | PyPI | Industry-standard linter; PyCQA project; large community |
| `fastapi` | `>=0.115` | PyPI | Top-tier Python web framework; security-conscious maintainers |
| `fastmcp` | `>=0.1` | PyPI | MCP server framework; actively developed; hash-verified |
| `pyyaml` | `>=6.0` | PyPI | Pinned to v6+ (safe load enforced); CVE history reviewed |
| `rich` | `>=13.0` | PyPI | Display-only; no network access; low risk |
| `uvicorn` | `>=0.32` | PyPI | ASGI server; widely used; actively maintained |
| `pathspec` | `>=0.12` | PyPI | File-pattern matching; no network access; low risk |
| `tabulate` | `>=0.9` | PyPI | Output formatting only; no network access; minimal risk |

> *This table must be updated in the release PR whenever dependencies are added, removed, or significantly upgraded.*

---

## 6. Vulnerability Triage Process — NIST RV.2.2

> *ISO 27001:2022 reference: A.8.8 (Management of technical vulnerabilities)*
> *COBIT 2019 reference: DSS05.07 (Monitor the Infrastructure for Security-Related Events), MEA03 (Managed Compliance)*
> *NIST SP 800-53 reference: RA-5 (Vulnerability Monitoring and Scanning), SI-2 (Flaw Remediation)*

### 6.1 Severity Classification and SLA

Vulnerabilities are classified using CVSS v3.1 base scores. The following SLA timelines apply:

| Severity | CVSS Range | Remediation SLA | Owner |
|----------|-----------|-----------------|-------|
| **Critical** | 9.0 – 10.0 | 24 hours — immediate hotfix release | Repository maintainer |
| **High** | 7.0 – 8.9 | 7 calendar days | Repository maintainer |
| **Medium** | 4.0 – 6.9 | 30 calendar days or next scheduled release | Repository maintainer |
| **Low** | 0.1 – 3.9 | 90 calendar days or backlog prioritisation | Repository maintainer |

### 6.2 Triage Process

1. **Intake** — Vulnerabilities are reported via the process defined in `SECURITY.md` (responsible disclosure). Public issues must **not** be opened for unpatched vulnerabilities.
2. **Assessment** — The maintainer assesses CVSS score, exploitability in the HotspotTriage deployment context (local tool, no network exposure), and affected component.
3. **Prioritisation** — Severity is assigned per Section 6.1. Context-adjusted severity may differ from base CVSS where the local-only deployment model eliminates certain attack vectors.
4. **Remediation** — A fix is developed on a private branch, reviewed, and released per the SLA above.
5. **Disclosure** — Following remediation, a public advisory is published via GitHub Security Advisories.
6. **Escalation** — If the SLA cannot be met (e.g., upstream dependency has no fix available), a mitigating control or workaround is documented and communicated.

### 6.3 Monitoring Activities — ISO 27001:2022 A.8.16

> *ISO 27001:2022 reference: A.8.16 (Monitoring activities)*
> *NIST SP 800-53 reference: SI-4 (System Monitoring), SI-2 (Flaw Remediation)*
> *COBIT 2019 reference: DSS05.07 (Monitor the Infrastructure for Security-Related Events)*

Security monitoring operates at two levels: **pre-merge** (CI pipeline) and **post-release** (continuous and scheduled).

#### Pre-merge controls (CI pipeline — every PR)

| Control | Tooling | Trigger |
|---------|---------|----------|
| Dependency vulnerability scan | Trivy (fs, CRITICAL/HIGH) | Every PR and push to `main` |
| Static code analysis (SAST) | GitHub CodeQL | Every PR and push to `main` |
| Secret scanning | Gitleaks | Every PR and push to `main` |
| Security gate | CI pass/fail block | Every PR — merge blocked on failure |

#### Post-release controls (continuous and scheduled)

| Control | Tooling | Cadence | Purpose |
|---------|---------|---------|----------|
| Dependency CVE monitoring | GitHub Dependabot | Continuous | Detects CVEs published against pinned dependencies post-release; alerts routed to maintainer via GitHub notifications |
| Scheduled filesystem scan | Trivy (fs, CRITICAL/HIGH) via `security.yml` cron | Weekly (Monday 02:00 UTC) | Catches newly published CVEs between releases |
| `uv.lock` CVE review | Manual `pip-audit` run | At every release milestone | Ensures no unaddressed CVEs exist in the locked dependency graph before tagging |

#### Post-release response SLA

When a CVE alert is received post-release (via Dependabot or Trivy scheduled scan), the response SLA from §6.1 applies:

| Severity | Triage deadline | Hotfix release deadline |
|----------|----------------|-------------------------|
| Critical (CVSS 9.0–10.0) | Within 24 hours of alert | Within 24 hours of confirmation |
| High (CVSS 7.0–8.9) | Within 48 hours of alert | Within 7 calendar days |
| Medium (CVSS 4.0–6.9) | Within 7 days of alert | Next scheduled release |
| Low (CVSS 0.1–3.9) | Backlog triage | Next scheduled release |

If an upstream dependency has no available fix within the SLA window, a documented mitigating control or workaround must be published as a GitHub Security Advisory. The hotfix process is defined in `docs/RELEASE_POLICY.md` §6.

---

## 7. Configuration Baseline — ISO 27001:2022 A.8.9

> *ISO 27001:2022 reference: A.8.9 (Configuration management)*
> *NIST SP 800-53 reference: CM-2 (Baseline Configuration), CM-3 (Configuration Change Control), CM-6 (Configuration Settings)*
> *COBIT 2019 reference: BAI10 (Manage Configuration)*

This section defines the authorised configuration baseline for HotspotTriage. Any deviation from this baseline must be introduced via a PR with at least one maintainer approval and reflected in an update to this document.

### 7.1 Runtime Environment

| Component | Authorised value | Enforcement |
|-----------|-----------------|-------------|
| Python version | 3.11, 3.12, or 3.13 | `requires-python = ">=3.11,<3.14"` in `pyproject.toml`; CI matrix in `tests.yml` |
| Package manager | `uv` (latest stable) | `uv.lock` present in repository root; all installs via `uv sync` |
| Dependency pinning | Hash-verified via `uv.lock` | `uv sync` enforces hash verification; direct `pip install` without lockfile is not permitted for production installs |
| Build backend | `hatchling` (PyPA-endorsed) | `[build-system] requires = ["hatchling"]` in `pyproject.toml`; produces wheel and sdist via `uv build` |

> **Note on Hatchling:** Hatchling is the build backend component of the [Hatch](https://hatch.pypa.io) project, maintained by the Python Packaging Authority (PyPA). It is invoked by `uv build` to produce the wheel (`.whl`) and source distribution (`.tar.gz`) release artefacts. It is a well-maintained, PyPA-endorsed standard with no network access at build time.

### 7.2 Code Quality Baseline

| Control | Requirement | Verification command |
|---------|-------------|---------------------|
| Linting | `pylint` score ≥ 9.0 across `src/hotspottriage/` | `uv run pylint src/hotspottriage --fail-under=9.0` |
| No Error/Fatal findings | Zero `pylint` E or F category findings | Included in above command output |
| Programmatic enforcement | `[tool.pylint.main] fail-under = 9.0` to be added to `pyproject.toml` | Tracked as a separate code-change PR |

### 7.3 Security Configuration Baseline

| Control | Requirement | Enforcement |
|---------|-------------|-------------|
| No hardcoded secrets | No secrets, credentials, or tokens in any file | Gitleaks on every PR (blocks merge) |
| Dashboard binding | `127.0.0.1` only | Implemented in [#84](https://github.com/avnovikov/HotspotTriage/issues/84); CodeQL verified |
| MCP transport | stdio only — no network socket | Architectural requirement; see §3.1 |
| Branch protection | Signed commits required on `main`; PRs require ≥1 approval | GitHub branch protection rules |
| Tag protection | Release tags (`v*`) protected — no force-push, no deletion | GitHub tag protection rules |

### 7.4 Change Control

Any change to the authorised configuration baseline defined in this section must:

1. Be proposed via a feature or docs PR referencing the relevant issue
2. Receive at least one maintainer approval before merge
3. Be reflected in an update to this section in the same PR
4. Be noted in `CHANGELOG.md` under `[Unreleased]`

---

## 8. Document Control

| Attribute | Value |
|-----------|-------|
| Created | 2026-05-09 |
| Last reviewed | 2026-05-09 |
| Next review | At next release milestone |
| Approved by | @avnovikov |
| Related documents | `SECURITY.md`, `CONTRIBUTING.md`, `docs/RELEASE_POLICY.md` |
