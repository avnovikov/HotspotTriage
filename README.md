# HotspotTriage

Rank Python hotspots where complexity meets churn—then wire that signal into your agent through MCP.

HotspotTriage analyzes tracked `.py` files in a Git repo, blends AST metrics (Radon) with history (`git log`), and per-function churn (in block mode), smells (Pylint heuristics), and block similarity (DeepCSIM).[file:1] It is a Python evolution of the idea behind [code-complexity](https://github.com/github/codeql/tree/main/python/ql/src/codeql/python/frameworks/Complexity), built for engineers and coding agents who want numbers, not guesswork. Open source (MIT). Python 3.11+.[file:1]

##  The Problem
Coding agents are not yet there—they churn out **duplicated, smelly, bad code**. You can run always-expensive models everywhere, but that's just **tokens burning**. Humans can't be fast enough for code review, and bad code slips into the repo. Even the best models can't do a good code review for various reasons.[file:1]

We need a mechanism to **automatically understand the problems with the code** and **route refactoring + the most expensive models to the particular areas, not everywhere**.[file:1]

##  The Solution
HotspotTriage makes the overlap visible **per file or per function**—so you can prioritize reviews, safer edits, and stronger models **where risk is highest**.[file:1]

![Web dashboard overview](docs/screenshots/dashboard-overview.png)
*The FastAPI UI (starts with `hotspottriage start-mcp-server --open-browser`): tool activity, logs, cache controls, and project context.

##  Key Benefits
- **MCP server**: expose analysis, cache lifecycle, and config scaffolding to Cursor, Claude Code, and other MCP clients (FastMCP).[file:1]
- **CLI**: table, JSON, or CSV output for CI and local exploration (`hotspottriage repo`).[file:1]
- **Block mode**: function/method rows with cached churn (`git log -L`), optional similarity, and interpretable risk bands for agent routing.[file:1]
- **Layered YAML config**: global, project, and local overrides (Serena-inspired layering); `hotspottriage init` scaffolds templates.[file:1]

## Who It's For
- Agent workflows: quantify risk before edits; route expensive reasoning to the worst hotspots.[file:1]
- Teams shipping Python: repeatable hotspot lists from CI or local runs.[file:1]
- Maintainers: one tool for complexity, churn, smells, and (in block mode) similarity pressure.[file:1]

## Quick Start

**Install** (from a clone—recommended for development, uses `uv.lock` when present):
```bash
git clone https://github.com/avnovikov/HotspotTriage.git
cd HotspotTriage
uv sync
```
Editable install with pip:
```bash
pip install -e .
```
After install, `hotspottriage`, `hotspottriage-mcp`, and `hotspottriage-cache` are on your PATH.[file:1]

**Run as an MCP Server** (follows the same pattern as Serena: `hotspottriage start-mcp-server` = stdio MCP). The `hotspottriage-mcp` entry point is an alias. While MCP talks over stdio, the process can also bring up a local web dashboard (FastAPI: logs, cache actions, and block metrics). Use `--open-browser` to open it when the server starts, `--no-dashboard` to disable it, or `--dashboard-port` / `--dashboard-host` to tune binding. See [ARCHITECTURE.md](ARCHITECTURE.md) for dashboard wiring.
```bash
uv run hotspottriage start-mcp-server --help
```
Ephemeral run from Git (can resync on upstream churn):
```bash
uvx -p 3.13 --from git+https://github.com/avnovikov/HotspotTriage hotspottriage start-mcp-server
```
Example MCP client config (matches this repo's `.cursor/mcp.json`; launcher injects `start-mcp-server` args—are dashboard flags such as `--open-browser`):
```json
{
  "mcpServers": {
    "hotspottriage": {
      "command": "path/to/HotspotTriage/scripts/run-hotspottriage-mcp.sh",
      "args": ["--open-browser"],
      "env": {
        "PATH": "path/to/HotspotTriage/.venv/bin:$PATH"
      }
    }
  }
}
```
Direct binary (same process, explicit subcommand):
```json
{
  "mcpServers": {
    "hotspottriage": {
      "command": "path/to/HotspotTriage/.venv/bin/hotspottriage",
      "args": ["start-mcp-server", "--open-browser"],
      "env": {
        "PATH": "path/to/HotspotTriage/.venv/bin:$PATH"
      }
    }
  }
}
```
For predictable tooling (e.g., pylint for smells), run from a dedicated venv and put that `bin` first on `PATH`. `scripts/run-hotspottriage-mcp.sh` prepends the project venv and execs `hotspottriage start-mcp-server`.[file:1]

**Tools exposed over MCP**: `analyze`, `generatecache`, `cachestatus`, `clearcache`, and `initconfig`. Pass `compact=false` on `analyze` when you need full metric rows.[file:1]

**Use with Claude Code**: discovers the server through its standard MCP config. From inside the cloned repo (so the launcher and venv resolve correctly):
```bash
claude mcp add hotspottriage -- ./scripts/run-hotspottriage-mcp.sh --open-browser
```
Or register it manually by adding the same block as above to `.claude.json` under `mcpServers` (the `.cursor/mcp.json` snippet works verbatim—Claude Code reads the same shape).[file:1]

Then in a Claude Code session: