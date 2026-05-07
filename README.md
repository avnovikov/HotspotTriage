# HotspotTriage

**Rank Python hotspots where complexity meets churn—then wire that signal into your agent through MCP.**

HotspotTriage analyzes **tracked** `.py` files in a Git repo, blends **AST metrics** ([Radon](https://github.com/rubik/radon)) with **history** (`git log`, and per-function churn in block mode), **smells** (Pylint + heuristics), and **block similarity** ([DeepCSIM](https://pypi.org/project/deepcsim/)). It is a Python evolution of the idea behind [`code-complexity`](https://github.com/simonrenoult/code-complexity)—built for engineers and coding agents who want numbers, not guesswork.

Open source (MIT). **Python 3.11–3.13.**

---

## Screenshots

**Web dashboard (Overview)** — the FastAPI UI that starts with the MCP server (`hotspottriage start-mcp-server --open-browser`): tool activity, logs, cache controls, and project context.

![HotspotTriage dashboard — Overview](docs/screenshots/dashboard-overview.png)

This file is a **real screenshot** of the running dashboard (not a mock). Replace [`docs/screenshots/dashboard-overview.png`](docs/screenshots/dashboard-overview.png) only when you intentionally refresh repo imagery — see [`docs/screenshots/README.md`](docs/screenshots/README.md).

---

## Why HotspotTriage

Refactors hurt most where two things collide: the code is **hard to reason about**, and teams **keep touching it**. HotspotTriage makes that overlap visible—per file or per function—so you can prioritize reviews, safer edits, and stronger models where risk is highest.

---

## What You Get

- **MCP server** — expose analysis, cache lifecycle, and config scaffolding to Cursor, Claude Code, and other MCP clients ([FastMCP](https://github.com/jlowin/fastmcp)).
- **CLI** — table, JSON, or CSV output for CI and local exploration (`hotspottriage <repo>`).
- **Block mode** — function/method rows with cached churn (`git log -L`), optional similarity, and interpretable risk bands for agent routing.
- **Layered YAML config** — global, project, and local overrides (Serena-inspired layering); `hotspottriage init` scaffolds templates.

---

## Install

**From a clone** (recommended for development; uses `uv.lock` when present):

```bash
git clone https://github.com/avnovikov/HotspotTriage.git
cd HotspotTriage
uv sync
```

**Editable install with pip:**

```bash
pip install -e .
```

After install, `hotspottriage`, `hotspottriage-mcp`, and `hotspottriage-cache` are on your PATH.

---

## Run as an MCP Server

HotspotTriage follows the same pattern as [Serena](https://github.com/oraios/serena): **`hotspottriage start-mcp-server`** (stdio MCP). The `hotspottriage-mcp` entry point is an alias.

While MCP talks over stdio, the process can also bring up a **local web dashboard** (FastAPI): logs, cache actions, and block metrics. Use **`--open-browser`** to open it when the server starts, **`--no-dashboard`** to disable it, or **`--dashboard-port`** / **`--dashboard-host`** to tune binding. See [ARCHITECTRE.md](ARCHITECTRE.md) for dashboard wiring.

```bash
uv run hotspottriage start-mcp-server --help
```

**Ephemeral run from Git** (can resync on upstream churn):

```bash
uvx -p 3.13 --from git+https://github.com/avnovikov/HotspotTriage hotspottriage start-mcp-server
```

**Example MCP client config** (matches this repo’s [`.cursor/mcp.json`](.cursor/mcp.json): launcher injects `start-mcp-server`; args are dashboard flags such as `--open-browser`):

```json
{
  "mcpServers": {
    "hotspottriage": {
      "command": "/path/to/HotspotTriage/scripts/run_hotspottriage_mcp.sh",
      "args": ["--open-browser"],
      "env": {
        "PATH": "/path/to/HotspotTriage/.venv/bin:${PATH}"
      }
    }
  }
}
```

**Direct binary** (same process, explicit subcommand):

```json
{
  "mcpServers": {
    "hotspottriage": {
      "command": "/path/to/HotspotTriage/.venv/bin/hotspottriage",
      "args": ["start-mcp-server", "--open-browser"],
      "env": {
        "PATH": "/path/to/HotspotTriage/.venv/bin:${PATH}"
      }
    }
  }
}
```

For predictable tooling (e.g. `pylint` for smells), run from a **dedicated venv** and put that `bin` first on `PATH`. [`scripts/run_hotspottriage_mcp.sh`](scripts/run_hotspottriage_mcp.sh) prepends the project venv and execs `hotspottriage start-mcp-server`.

**Tools exposed over MCP** include `analyze`, `generate_cache`, `cache_status`, `clear_cache`, and `init_config`. Pass `compact=false` on `analyze` when you need full metric rows.

### Use with Claude Code

[Claude Code](https://docs.claude.com/en/docs/claude-code) discovers the server through its standard MCP config. From inside the cloned repo (so the launcher and venv resolve correctly):

```bash
claude mcp add hotspottriage -- ./scripts/run_hotspottriage_mcp.sh --open-browser
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
- For your own projects, drop a `CLAUDE.md` at the repo root pointing at the modules you care about; Claude Code auto-loads it as system context. The architecture map in [ARCHITECTRE.md](ARCHITECTRE.md) and the scoring guide in [SCORES.md](SCORES.md) are good things to point at from yours.


---

## Who It’s For

- **Agent workflows** — quantify risk before edits; route expensive reasoning to the worst hotspots.
- **Teams shipping Python** — repeatable hotspot lists from CI or local runs.
- **Maintainers** — one tool for complexity, churn, smells, and (in block mode) similarity pressure.

---

## Learn More

| Doc | What’s inside |
|-----|----------------|
| [ARCHITECTRE.md](ARCHITECTRE.md) | Pipeline, caching, dashboard, MCP wiring, module map |
| [SCORES.md](SCORES.md) | Metrics, normalization, composite score, risk bands |
| [docs/block-cache-model.md](docs/block-cache-model.md) | Block cache format and semantics |

Developing this repo: run **`uv lock`** after dependency changes in `pyproject.toml`. Run **`pytest`** (or `uv run pytest`) before merging; architecture notes live in [ARCHITECTRE.md](ARCHITECTRE.md) above.
