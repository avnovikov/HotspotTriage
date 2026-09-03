# Changelog

All notable changes to HotspotTriage are documented here.
This project adheres to [Semantic Versioning](https://semver.org/) and [Keep a Changelog](https://keepachangelog.com/).

> SOC 2 CC8.1: Authorizes and documents changes before implementation.

---

## [Unreleased]

### Fixed
- Block cache (`blocks.pkl`) never stores rows for paths matching the repo
  `.gitignore` (save/load/`BlockCacheManager`); dashboard heatmap stays clean (#204).

### Security
- Bump lockfile / constraints to clear open Dependabot alerts on `mcp`, `starlette`,
  `cryptography`, `pyjwt`, `joserfc`, `python-multipart`, `pydantic-settings`, and
  `idna` (#202).

### Fixed
- Dashboard route existence test uses OpenAPI paths (compatible with Starlette/FastAPI
  included-router changes after the security upgrades).
- Rename architecture doc `ARCHITECTRE.md` → `ARCHITECTURE.md` (typo; #147).
- Correct `README.md` links from `docs/screenshots/README.md` (paths must reach the repo root).
- Replace broken in-repo hyperlink to `.cursor` skills in branch-protection audit evidence with a workstation-local path description (#147).

### Added
- MCP `analyze` optional `include_summary` adds a `summary` aggregate over the full pre-`limit` block set (#157).
- MCP `analyze` JSON responses include a `metadata` object (git provenance, `analyzed_at`, effective filters, row counts, `config_fingerprint`) (#156).
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
