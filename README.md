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

Code agents are fast but blind. They lack understanding about which parts of a codebase are risky, so they introduce duplication, maintainability debt, and code smells even when tests go green. Teams compensate by using their most powerful (and expensive) models on everything, or relying on human reviewers who cannot review every diff. The result: quality problems accumulate in the areas that matter most, undetected.

## 💡 The Solution

HotspotTriage makes the "code risk score" visible at the function level, enabling you to rank reviews and apply compute power only where it matters. By integrating directly into your agentic workflow, it allows models to self-assess: should this code be refactored first? Which model is needed for this task? Did this change improve the code? Your agents shift from ignorance to being data-informed, making code quality a first-class citizen in their decisions.

HotspotTriage's composite code risk score isn't fixed — it's fully tunable via config coefficients. Prioritize smells over complexity? Increase Pylint weight. Focus on duplication? Dial up DeepCSIM similarity. As team priorities evolve with cleanup sprints or big refactors, tweak the sliders and your agents adapt immediately.

Engineers stay in control: the metric adapts with your real pain points, ensuring agents target duplication patterns, complexity spikes, and maintainability red flags exactly where humans see the biggest risks.

---

![Web dashboard overview](docs/screenshots/dashboard-overview.png)

*The FastAPI UI (starts with `hotspottriage start-mcp-server --open-browser`): tool activity, logs, cache controls, and project context. This is a real screenshot of the running dashboard (not a mock). *

## Key Benefits

- **MCP server**: plug HotspotTriage directly into Cursor, Claude Code, or any MCP client — agents get live risk scores without leaving their workflow.
- **CLI**: table, JSON, or CSV output — drop it into CI pipelines or run it locally with a single command (`hotspottriage <repo>`).
- **Block mode**: scores at the function/method level — not just per file — so agents know *exactly* which block to target, not just which file.

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
