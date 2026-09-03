# Changelog

All notable changes to HotspotTriage are documented here.
This project adheres to [Semantic Versioning](https://semver.org/) and [Keep a Changelog](https://keepachangelog.com/).

> SOC 2 CC8.1: Authorizes and documents changes before implementation.

---

## [Unreleased]

---

## [0.2.0] — 2026-09-03

Minor release focused on dashboard UX, cache correctness, and tunable churn decay —
plus a dependency security refresh.

### Highlights

1. **Gitignore-safe block cache** (#204) — paths matching `.gitignore` never enter
   `blocks.pkl` / the block cache DB, so the dashboard heatmap stays clean by default.
2. **One dashboard per project directory** (#206) — if a healthy dashboard is already
   running for the same cwd, HotspotTriage reuses it (no second port bind, no second
   browser window).
3. **Churn decay half-life in hours** (#208) — configure `decay_half_life_hours`
   (default **1**) in YAML and on the dashboard Config page; legacy seconds values
   migrate on load.

### Changed

- Churn decay half-life is configured as **`decay_half_life_hours`** (default **1** hour)
  instead of `decay_half_life` in seconds / 30-day default (#208). Editable on the
  dashboard Config page and via `/api/config/patch`. Legacy `decay_half_life`
  (seconds) in YAML is migrated to hours on load.

### Added

- Reuse an existing local dashboard for the same project directory instead of
  binding another port or opening another browser (#206).
- MCP `analyze` optional `include_summary` adds a `summary` aggregate over the full
  pre-`limit` block set (#157).
- MCP `analyze` JSON responses include a `metadata` object (git provenance,
  `analyzed_at`, effective filters, row counts, `config_fingerprint`) (#156).
- MCP structured tool errors: `{"error": {"code", "message", "details"}}` (#158).
- SOC 2 / compliance scaffolding: `SECURITY.md`, `CODEOWNERS`, `dependabot.yml`,
  security scanning workflow (CodeQL, Trivy, Gitleaks), pre-commit hooks, and this
  changelog.

### Fixed

- Block cache (`blocks.pkl`) never stores rows for paths matching the repo
  `.gitignore` (save/load/`BlockCacheManager`); dashboard heatmap stays clean (#204).
- Dashboard route existence test uses OpenAPI paths (compatible with Starlette/FastAPI
  included-router changes after the security upgrades).
- Rename architecture doc `ARCHITECTRE.md` → `ARCHITECTURE.md` (typo; #147).
- Correct `README.md` links from `docs/screenshots/README.md` (paths must reach the
  repo root).
- Replace broken in-repo hyperlink to `.cursor` skills in branch-protection audit
  evidence with a workstation-local path description (#147).

### Security

- Bump lockfile / constraints to clear open Dependabot alerts on `mcp`, `starlette`,
  `cryptography`, `pyjwt`, `joserfc`, `python-multipart`, `pydantic-settings`, and
  `idna` (#202).

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
