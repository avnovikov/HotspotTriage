# HotspotTriage

Rank Python hotspots where complexity meets churn—then wire that signal into your agent through MCP.

HotspotTriage analyzes tracked `.py` files in a Git repo, blends AST metrics (Radon) with history (`git log`), and per-function churn (in block mode), smells (Pylint heuristics), and block similarity (DeepCSIM).'' Built for engineers and coding agents who want numbers, not guesswork. Open source (MIT). Python 3.11+.''

## The Problem
Coding agents are not yet there—they churn out **duplicated, smelly, bad code**. You can run always-expensive models everywhere, but that's just **tokens burning**. Humans can't be fast enough for code review, and bad code slips into the repo. Even the best models can't do a good code review for various reasons.''

We need a mechanism to **automatically understand the problems with the code** and **route refactoring + the most expensive models to the particular areas, not everywhere**.''

## 💡 The Solution
HotspotTriage makes the overlap visible **per file or per function**—so you can prioritize reviews, safer edits, and stronger models **where risk is highest**.'' Coding agents can automatically unerstand which model to use, if the code should be refactored before the start of the change, if the changes improved the code or make it worth. After a few iterations your coding agents will start to pay attention to the numbers and after some time general code quality will be improved automagically. 

![Web dashboard overview](docs/screenshots/dashboard-overview.png)
*The FastAPI UI (starts with `hotspottriage start-mcp-server --open-browser`): tool activity, logs, cache controls, and project context. This is a real screenshot of the running dashboard (not a mock). Replace `docs/screenshots/dashboard-overview.png` only when you intentionally refresh repo imagery (see `docs/screenshots/README.md`).*''

##  Key Benefits
- **MCP server**: expose analysis, cache lifecycle, and config scaffolding to Cursor, Claude Code, and other MCP clients (FastMCP).''
- **CLI**: table, JSON, or CSV output for CI and local exploration (`hotspottriage repo`).''
- **Block mode**: function/method rows with cached churn (`git log -L`), optional similarity, and interpretable risk bands for agent routing.''
- **Layered YAML config**: global, project, and local overrides (Serena-inspired layering); `hotspottriage init` scaffolds templates.''

##  Who It's For
- Agent workflows: quantify risk before edits; route expensive reasoning to the worst hotspots.''
- Teams shipping Python: repeatable hotspot lists from CI or local runs.''
- Maintainers: one tool for complexity, churn, smells, and (in block mode) similarity pressure.''

##  Quick Start

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
After install, `hotspottriage`, `hotspottriage-mcp`, and `hotspottriage-cache` are on your PATH.''

**Run as an MCP Server**  The `hotspottriage-mcp` entry point is an alias. While MCP talks over stdio, the process can also bring up a local web dashboard (FastAPI: logs, cache actions, and block metrics). Use `--open-browser` to open it when the server starts, `--no-dashboard` to disable it, or `--dashboard-port` / `--dashboard-host` to tune binding. See [ARCHITECTURE.md](ARCHITECTURE.md) for dashboard wiring.
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
For predictable tooling (e.g., pylint for smells), run from a dedicated venv and put that `bin` first on `PATH`. `scripts/run-hotspottriage-mcp.sh` prepends the project venv and execs `hotspottriage start-mcp-server`.''

**Tools exposed over MCP**: `analyze`, `generatecache`, `cachestatus`, `clearcache`, and `initconfig`. Pass `compact=false` on `analyze` when you need full metric rows.''

**Use with Claude Code**: discovers the server through its standard MCP config. From inside the cloned repo (so the launcher and venv resolve correctly):
```bash
claude mcp add hotspottriage -- ./scripts/run-hotspottriage-mcp.sh --open-browser
```
Or register it manually by adding the same block as above to `~/.claude.json` under `mcpServers` (the `.cursor/mcp.json` snippet works verbatim — Claude Code reads the same shape). Then in a Claude Code session:

```text
/mcp                                    # confirm "hotspottriage" is connected
> Use hotspottriage analyze on this repo, top 15 by score
> Then call generate_cache so the dashboard heatmap is populated
```

Tips:
- The first `analyze` call on a large repo populates `<repo>/.hotspottriage/cache/blocks.pkl`; subsequent calls are instant. Run `generate_cache` once up front to warm it deliberately.
- Project-level `.hotspottriage/project.yml` is **not** read by the MCP server (only by the CLI). Pass overrides as tool arguments, or change them via the dashboard config view.
- For your own projects, drop a `CLAUDE.md` at the repo root pointing at the modules you care about; Claude Code auto-loads it as system context. 


---

## Learn More

| Doc | What’s inside |
|-----|----------------|
| [ARCHITECTRE.md](ARCHITECTRE.md) | Pipeline, caching, dashboard, MCP wiring, module map |
| [SCORES.md](SCORES.md) | Metrics, normalization, composite score, risk bands |
| [docs/block-cache-model.md](docs/block-cache-model.md) | Block cache format and semantics |

Developing this repo: run **`uv lock`** after dependency changes in `pyproject.toml`. Run **`pytest`** (or `uv run pytest`) before merging; architecture notes live in [ARCHITECTRE.md](ARCHITECTRE.md) above.
