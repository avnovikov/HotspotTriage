# Changelog

All notable changes to HotspotTriage are documented here.
This project adheres to [Semantic Versioning](https://semver.org/) and [Keep a Changelog](https://keepachangelog.com/).

> SOC 2 CC8.1: Authorizes and documents changes before implementation.

---

## [Unreleased]

### Added
- SOC 2 compliance files: `SECURITY.md`, `CODEOWNERS`, `dependabot.yml`
- Security scanning workflow: CodeQL, Trivy, Gitleaks
- Pre-commit hooks for secret scanning and linting
- `CHANGELOG.md` for audit trail

---

## [0.1.0] — 2026-05-04

### Added
- Initial release of HotspotTriage
- MCP-powered Python codebase analysis
- Complexity, churn, and duplication scoring via `radon`
- Agent routing: automation, LLM, or human review
- FastAPI server + MCP server entrypoints
- CLI interface (`hotspottriage`)
- Architecture documentation (`ARCHITECTURE.md`)
