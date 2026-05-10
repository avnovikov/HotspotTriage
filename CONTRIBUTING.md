# Contributing to HotspotTriage

> **NIST SSDF reference:** PO.1.1 — Implement a security policy for the software development lifecycle
> *ISO 27001:2022: A.5.1 (Policies), A.8.32 (Change management), A.6.3 (Information security awareness)*
> *COBIT 2019: APO01 (Manage the IT Management Framework), BAI06 (Manage IT Changes)*

Thank you for your interest in HotspotTriage. This document defines the secure development lifecycle policy for all contributors.

---

## 1. Development Environment Setup

### 1.1 Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11 – 3.13 | Runtime (matches `requires-python` in `pyproject.toml`) |
| [`uv`](https://github.com/astral-sh/uv) | Latest stable | Package manager, virtualenv, build |
| Git | ≥ 2.34 | Version control (SSH signing support) |

### 1.2 Install dependencies

```bash
git clone https://github.com/avnovikov/HotspotTriage.git
cd HotspotTriage
uv sync --all-extras --dev
```

This installs all runtime and development dependencies into an isolated virtualenv managed by `uv`, using hash-verified versions from `uv.lock`.

### 1.3 SSH Commit and Tag Signing (required)

All commits to this repository **must be SSH-signed**. This is enforced by the branch protection rule on `main` — unsigned commits will be rejected.

**One-time workstation setup:**

```bash
# Use SSH for signing (no GPG keyring required)
git config --global gpg.format ssh
git config --global user.signingKey ~/.ssh/id_ed25519.pub   # replace with your key path
git config --global commit.gpgSign true    # auto-sign all commits
git config --global tag.gpgSign true       # auto-sign all tags
```

**GitHub setup:** Register your SSH key under **Settings → SSH and GPG keys** as a *Signing Key* (separate from your authentication key). GitHub will display a `Verified` badge on your signed commits.

> *This two-layer signing policy (commits + tags) establishes an unbroken chain of custody from individual change to release, satisfying NIST SSDF PS.3.1 and ISO 27001:2022 A.8.32. See `docs/RELEASE_POLICY.md` §4.1 for the full signing rationale.*

### 1.4 Pre-commit Hooks

Pre-commit hooks are **planned** for a future milestone. Once available, setup will be:

```bash
uv run pre-commit install
```

Until then, run linting and security checks manually before opening a PR (see Sections 4 and 5).

---

## 2. Branching and Pull Request Policy

> *NIST SSDF PW.6.1 — review and merge code changes*
> *ISO 27001:2022: A.8.32 (Change management)*

- **No direct pushes to `main`.** All changes must go through a feature branch and PR.
- **Branch naming convention:**

| Type | Pattern | Example |
|------|---------|------------------------------------------------------|
| Feature | `feature/issue-NNN-short-description` | `feature/issue-42-score-explainer` |
| Bug fix | `fix/issue-NNN-short-description` | `fix/issue-99-path-injection` |
| Release | `release/vX.Y.Z` | `release/v1.1.0` |
| Hotfix | `hotfix/vX.Y.Z` | `hotfix/v1.0.1` |
| Docs | `docs/issue-NNN-short-description` | `docs/issue-108-contributing` |

- **Every PR must:**
  - Reference the related issue (`Closes #NNN` or `Relates to #NNN` in the PR body)
  - Have **at least one approval** from a maintainer before merge
  - Pass all CI checks: `tests.yml` (pytest matrix, Python 3.11–3.13) and `security.yml` (CodeQL, Trivy, Gitleaks)
  - Contain only SSH-signed commits — unsigned commits block merge via branch protection

- **Squash or merge commits** are both acceptable; rebase is preferred for clean history on feature branches.

---

## 3. Secure Coding Standards

> *NIST SSDF PW.1.1 — define security requirements; PW.4.1 — vet components*
> *ISO 27001:2022: A.8.26 (Application security requirements), A.8.25 (Secure development lifecycle)*

- **Follow OWASP Top 10** principles where applicable, particularly injection prevention, broken access control, and security misconfiguration.
- **No hardcoded secrets or credentials** in source code, configuration files, or tests. Secret scanning (Gitleaks) runs on every PR and will block merge if secrets are detected.
- **Input validation is required** for all user-facing or API-facing inputs. Use Pydantic models at trust boundaries. See `docs/SECURITY_REQUIREMENTS.md` §4 for full requirements and implementation evidence.
- **New dependencies must pass the vetting checklist** in `docs/SECURITY_REQUIREMENTS.md` §5.1 before being added. Document vetting evidence in the PR body.
- **`pylint` must score ≥ 9.0** across `src/hotspottriage/`:
  ```bash
  uv run pylint src/hotspottriage --fail-under=9.0
  ```
- **Path operations** must use the centralised `path_utils.resolve_local_repo_path()` utility — never raw string concatenation or `os.path.join` with untrusted input.

---

## 4. Testing

> *NIST SSDF PW.7.2 — test the software to identify vulnerabilities*
> *ISO 27001:2022: A.8.29 (Security testing in development and acceptance), A.8.33 (Protection of test information)*

- **New features must include corresponding tests** in `tests/`.
- **Bug fixes must include a regression test** that reproduces the bug before the fix.
- Run the full test suite locally before opening a PR:
  ```bash
  uv run pytest tests/ -v
  ```
- Tests run automatically in CI against **Python 3.11, 3.12, and 3.13** via `tests.yml` (issue #106, completed).
- Test coverage of valid, invalid, oversized, and boundary inputs is expected for any code touching input validation or scoring logic.

### 4.1 Test Data Policy (ISO 27001:2022 A.8.33)

All test fixtures in `tests/` use **synthetic Python source code samples** — no real user data, no personal data, and no production repository code. No secrets, credentials, or sensitive information are present in the test directory; this is enforced by Gitleaks secret scanning on every PR. If real code samples are ever proposed as test fixtures in a future contribution, they must be reviewed for sensitive content by the maintainer before the PR is merged.

---

## 5. Security

> *NIST SSDF RV.2.2 — address vulnerabilities*
> *ISO 27001:2022: A.8.8 (Management of technical vulnerabilities)*

### 5.1 Reporting Vulnerabilities

**Do not open public GitHub issues for security vulnerabilities.** Follow the responsible disclosure process defined in `SECURITY.md`.

### 5.2 Pre-PR Security Checks

Run the following locally before opening a PR that touches dependencies or security-sensitive code:

```bash
# Dependency vulnerability scan
uv export --format requirements-txt | pip-audit -r /dev/stdin

# Lint for security anti-patterns
uv run pylint src/hotspottriage --fail-under=9.0
```

CI runs CodeQL (SAST), Trivy (dependency + fs scan), and Gitleaks (secret scanning) automatically on every PR via `security.yml`.

---

## 6. Release Process

> *NIST SSDF PS.3.1 — archive and protect each release version*

Only maintainers may create release tags. The full release process, pre-release gate checklist, versioning policy, and hotfix process are defined in **`docs/RELEASE_POLICY.md`**.

Key points for contributors:
- Version bumps happen in the release PR — do not bump `version` in `pyproject.toml` in feature PRs
- `CHANGELOG.md` is updated as part of the release PR — add your changes to the `[Unreleased]` section in your feature PR if appropriate
- All release tags are SSH-signed (configured in Section 1.3 above)

---

## 7. Access Control Policy (UK Cyber Essentials alignment)

> *UK Cyber Essentials: Access Control — documented user access rights*
> *ISO 27001:2022: A.5.15–5.18 (Access control, identity management)*
> *NIST SP 800-53: AC-2, AC-3 (Account management, access enforcement)*
> *COBIT 2019: DSS05 (Manage Security Services)*

### 7.1 Principle of least privilege

Access to repository functions is granted on a least-privilege basis. Each role is assigned only the rights necessary to perform its function.

| Role | Rights | Controls |
|------|--------|----------|
| Maintainer | Merge to `main`, publish releases, manage branch protection | SSH-signed commits and GitHub repo admin |
| Contributor | Open PRs, push to feature branches | Fork or branch + SSH-signed commits |
| Read-only | View code, open issues | GitHub public access |

### 7.2 Branch protection rules

- The `main` branch is protected: direct pushes are prohibited.
- All changes to `main` must go through a Pull Request.
- At least one approval is required (self-approval is documented for solo maintainer with rationale).
- Status checks (CI, security scans) must pass before merge.
- All commits must be SSH-signed (see Section 1.3).

### 7.3 Release rights

Only the designated maintainer (`@avnovikov`) may create signed release tags and publish GitHub Releases. Release tags must be SSH-signed (enforced by policy; see `docs/RELEASE_POLICY.md`).

### 7.4 Access review cadence

Access rights are reviewed at least annually or upon any maintainer change. The review is conducted by `@avnovikov` and documented in the release changelog.

| Regulation / standard | Control | Requirement |
|------------------------|---------|---------------|
| UK Cyber Essentials | Access Control | Documented user access rights |
| UK Cyber Essentials Plus | Access Control | Verified access control implementation |
| ISO 27001:2022 | A.5.15–5.18 | Access control, identity management |
| NIST SP 800-53 | AC-2, AC-3 | Account management, access enforcement |
| COBIT 2019 | DSS05 | Manage Security Services |

---

## 8. Use of AI

HotspotTriage is an AI-tooling project and the maintainer uses AI assistance (including MCP-based agents) in development. Contributors are welcome to use AI tools, subject to the following:

- **You are responsible for all code you submit**, regardless of how it was generated. Review AI-generated code carefully before committing.
- **AI-generated code must meet all the same standards** as human-written code: tests, input validation, pylint score, security review.
- **Do not submit AI-generated dependency additions** without manually completing the vetting checklist in `docs/SECURITY_REQUIREMENTS.md` §5.1.
- **Disclose AI assistance in the PR description** if a significant portion of the implementation was AI-generated. This supports audit transparency.

---

## 9. Code of Conduct

This project follows the [Contributor Covenant v2.1](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).

Instances of unacceptable behaviour may be reported to the maintainer at the email address listed in `pyproject.toml`.

---

## Document Control

| Attribute | Value |
|-----------|-------|
| Created | 2026-05-09 |
| Last reviewed | 2026-05-09 |
| Next review | At next release milestone |
| Approved by | @avnovikov |
| Related documents | `SECURITY.md`, `docs/SECURITY_REQUIREMENTS.md`, `docs/RELEASE_POLICY.md`, `CHANGELOG.md` |
