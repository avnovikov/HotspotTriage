# HotspotTriage

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?style=flat)](LICENSE) [![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-blue?style=flat&logo=python)](pyproject.toml) [![Security Scans](https://github.com/avnovikov/HotspotTriage/actions/workflows/security.yml/badge.svg)](https://github.com/avnovikov/HotspotTriage/actions/workflows/security.yml) [![Tests](https://github.com/avnovikov/HotspotTriage/actions/workflows/tests.yml/badge.svg)](https://github.com/avnovikov/HotspotTriage/actions/workflows/tests.yml) [![SSH Signed](https://img.shields.io/badge/Commits-SSH%20Signed-green?style=flat&logo=git)](CONTRIBUTING.md#13-ssh-commit-and-tag-signing-required) [![Compliance](https://img.shields.io/badge/Compliance-SOC2%20%7C%20NIST%20%7C%20ISO%2027001%20%7C%20EU%20CRA-blue?style=flat)](docs/Compliance.md)

**Coding agents keep making a mess. Show them where their problems lie.**

HotspotTriage scores every function in your Python repo — blending complexity, churn,
smells, and duplication — so Cursor and Claude Code know exactly where to focus.

```bash
uvx -p 3.13 --from git+https://github.com/avnovikov/HotspotTriage \
  hotspottriage start-mcp-server --open-browser --default-target /path/to/your/repo
```

> Built for regulated and audited pipelines. See [Compliance](docs/compliance.md).

HotspotTriage analyzes tracked `.py` files in a Git repo, blends AST metrics (Radon) with history (`git log`), per-function churn (in block mode), smells (Pylint heuristics), and block similarity (DeepCSIM) — all wired through MCP for integration with agents.

Designed for engineers and coding agents who want precise, actionable metrics to improve coding style, accelerate refactoring, and boost code quality.


![Geiser Control Room](docs/screenshots/geiser_conrolroom.png)

## The Problem

Even with real breakthroughs like Claude Opus 4.5 and GPT‑5.3‑Codex — frontier models that pushed agentic coding, planning, and code quality forward in late 2025 and early 2026 — the core problems remain:

Coding agents fall short: they regularly introduce duplicated, hard-to-maintain, and smell-prone code into real codebases, even when it passes basic tests.

Running only the most expensive models on every change wastes tokens and slows teams down, without guaranteeing better engineering outcomes.

Human reviewers cannot keep up with every diff in fast-moving repositories, so quality issues still slip through. And even top-tier models are not yet reliable, end‑to‑end code reviewers: they lack full architectural context, can misinterpret nuanced requirements, and often miss performance, maintainability, and security concerns that still require static analysis and focused human review.

We need a mechanism to automatically identify code problems and route refactoring and expensive models to relevant areas, not everywhere.

## 💡 The Solution

HotspotTriage makes the overlap visible per file or function, so you can prioritize reviews, make safer edits, and use stronger models where risk is highest. Coding agents can automatically determine which model to use, whether code should be refactored before changes, whether changes improved the code, and whether they were worth it. After a few iterations, your coding agents will start paying attention to the numbers, and over time, general code quality will improve automagically.

HotspotTriage's composite score isn't fixed — it's fully customizable through normalization coefficients that let you dial in what matters most right now. Want to prioritize code smells over raw complexity? Crank up the Pylint heuristics weight. Obsessed with duplication? Boost DeepCSIM's block similarity factor. As your team's priorities shift — maybe code smells during cleanup season, or churn during a big refactor — you simply adjust the sliders in the config, and your agents adapt instantly.

This puts engineers in control: the metric evolves alongside your codebase's real pain points, ensuring agents focus on where humans see the biggest risks — whether that's eliminating duplication patterns, taming cyclomatic complexity spikes, or catching maintainability red flags before they spread.

---

![Web dashboard overview](docs/screenshots/dashboard-overview.png)

*The FastAPI UI (starts with `hotspottriage start-mcp-server --open-browser`): tool activity, logs, cache controls, and project context. This is a real screenshot of the running dashboard (not a mock). *

## Key Benefits

- **MCP server**: expose analysis, cache lifecycle, and config scaffolding to Cursor, Claude Code, and other MCP clients (FastMCP).
- **CLI**: table, JSON, or CSV output for CI and local exploration (`hotspottriage <repo>`).
- **Block mode**: function/method rows with cached churn (`git log -L`), optional similarity, and interpretable risk bands for agent routing.
- **Layered YAML config**: global, project, and local overrides (Serena-inspired layering); `hotspottriage init` scaffolds templates.

## Quick Start

**Try it now — no install:**
```bash
uvx -p 3.13 --from git+https://github.com/avnovikov/HotspotTriage \
  hotspottriage start-mcp-server --open-browser --default-target /path/to/your/repo
```

**Install for daily use with Cursor / Claude Code:**
```bash
git clone https://github.com/avnovikov/HotspotTriage.git && \
  cd HotspotTriage && ./scripts/install_hotspottriage.sh --venv
```
Requires Python 3.11–3.13. → [Full install options and troubleshooting](docs/INSTALL.md)

### Connect to your agent

**Cursor** — save as `.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "hotspottriage": {
      "command": "path/to/HotspotTriage/scripts/run_hotspottriage_mcp.sh",
      "args": ["--open-browser", "--default-target", "${workspaceFolder}"]
    }
  }
}
```

**Claude Code** — from inside the cloned repo:
```bash
claude mcp add hotspottriage -- ./scripts/run_hotspottriage_mcp.sh \
  --open-browser --default-target /path/to/your/repo
```

→ [All config variants, PATH/git troubleshooting](docs/INSTALL.md#troubleshooting)

**Make it a standing rule for agents:** Add the workflow from [`docs/agent-hotspottriage-score-check.md`](docs/agent-hotspottriage-score-check.md) to your repo's **`CLAUDE.md`**, Cursor **Rules**, or Copilot instructions — so agents run `analyze` on the target block before editing.

---

## Learn More

| Doc | What's inside |
|-----|----------------|
| [docs/INSTALL.md](docs/INSTALL.md) | Full install guide: all options, MCP server flags, Cursor/Claude Code configs, troubleshooting |
| [docs/agent-hotspottriage-score-check.md](docs/agent-hotspottriage-score-check.md) | MCP score check before editing hotspots (agent workflow) |
| [ARCHITECTRE.md](ARCHITECTRE.md) | Pipeline, caching, dashboard, MCP wiring, module map |
| [SCORES.md](SCORES.md) | Metrics, normalization, composite score, risk bands |
| [CONTRIBUTING.md](CONTRIBUTING.md#13-ssh-commit-and-tag-signing-required) | SSH-signed commits and tags setup (one-time workstation config) |
| [SUPPORT.md](SUPPORT.md) | Support policy, supported versions, EOL process (UK PSTI / EU CRA) |
| [SECURITY.md](SECURITY.md) | Security policy, VDP, regulatory cross-reference mapping |
| [docs/compliance.md](docs/compliance.md) | Full compliance posture: SOC2, NIST, ISO 27001, EU CRA, GDPR |
