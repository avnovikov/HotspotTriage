# Installation & Setup

> For a quick try with no install, see the [README Quick Start](../README.md#quick-start).  
> Requires **Python 3.11, 3.12, or 3.13** — see [Python version](#python-version) below.

---

## Python Version

HotspotTriage requires **Python 3.11, 3.12, or 3.13** (`requires-python` matches **deepcsim** on PyPI). On **3.14+**, pip reports `No matching distribution found for deepcsim` — use a supported interpreter. The install script checks this early and exits with a clear message if the version is unsupported.

---

## Install from Clone (Recommended)

Handles version check, `pip` upgrade, and editable install:

```bash
git clone https://github.com/avnovikov/HotspotTriage.git
cd HotspotTriage
./scripts/install_hotspottriage.sh --venv
```

**Script flags:**

- **`--venv`** — create/use `.venv` under the repo (recommended)
- **`--uv`** — run `uv sync` instead of pip (requires [`uv`](https://docs.astral.sh/uv/) and `uv.lock`)
- **`--python /path/to/python3.13`** — pick an interpreter if `python3` on `PATH` is too new

After install, `hotspottriage`, `hotspottriage-mcp`, and `hotspottriage-cache` are on your `PATH` when the venv is active.

---

## Manual Install

```bash
uv sync
```

```bash
python3.13 -m venv .venv && .venv/bin/python -m pip install --upgrade pip && .venv/bin/python -m pip install -e .
```

Editable install (only when active interpreter is already 3.11–3.13):

```bash
pip install -e .
```

---

## Run as MCP Server

HotspotTriage exposes an MCP server over **stdio**. The same process also launches the local FastAPI dashboard.

```bash
uv run hotspottriage start-mcp-server --help
```

**Key flags:**

| Flag | Description |
|------|-------------|
| `--open-browser` | Open the dashboard when the server starts |
| `--no-dashboard` | Disable the dashboard entirely |
| `--default-target PATH` | Repo to analyse when MCP tools omit `target` |
| `--dashboard-port PORT` | Dashboard port (default: 8000) |
| `--dashboard-host HOST` | Dashboard host (default: 127.0.0.1) |

**One-off run from Git (zero-install):**

```bash
uvx -p 3.13 --from git+https://github.com/avnovikov/HotspotTriage \
  hotspottriage start-mcp-server --open-browser --default-target /absolute/path/to/your/repo
```

---

## Use with Cursor

Save as `.cursor/mcp.json` in your workspace (or merge into Cursor's global MCP settings):

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

**Direct binary variant** (if shell wrappers don't work on your MCP host):

```json
{
  "mcpServers": {
    "hotspottriage": {
      "command": "path/to/HotspotTriage/.venv/bin/hotspottriage",
      "args": ["start-mcp-server", "--open-browser", "--default-target", "/absolute/path/to/your/repo"],
      "env": {
        "PATH": "/path/to/HotspotTriage/.venv/bin:/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"
      }
    }
  }
}
```

---

## Use with Claude Code

From inside the cloned repo:

```bash
claude mcp add hotspottriage -- ./scripts/run_hotspottriage_mcp.sh \
  --open-browser --default-target /absolute/path/to/your/repo
```

Or add manually to `~/.claude.json` under `mcpServers` (same JSON shape as Cursor above). Then in a Claude Code session:

```text
/mcp                          # confirm "hotspottriage" is connected
> Use hotspottriage analyze on this repo, top 15 by score
> Then call generate_cache so the dashboard heatmap is populated
```

---

## MCP Tools Reference

**Tools exposed:** `analyze`, `generate_cache`, `cache_status`, `clear_cache`, `init_config`.

Default `analyze` rows are **compact** (`function`, `score`, `risk_band`, `proposed_model`, `score_driver`, `rationale`). Pass `compact=false` for full metrics, `score_explanation`, and multi-line `score_narrative`.

**Tips:**

- With `--default-target`, tools can pass an empty `target` for that repo.
- The first `analyze` call on a large repo populates `.hotspottriage/cache/blocks.pkl`; subsequent calls are instant. Run `generate_cache` once upfront to warm it deliberately.
- Project-level `.hotspottriage/project.yml` is **not** read by the MCP server (only by the CLI). Pass overrides as tool arguments or change them via the dashboard config view.

---

## Troubleshooting

### `[Errno 2] No such file or directory: 'git'`

Cursor and Claude Code often start MCP with a minimal `PATH`. The launcher script (`run_hotspottriage_mcp.sh`) prepends `.venv/bin` and common system directories (`/usr/bin`, `/bin`, `/usr/local/bin`, `/opt/homebrew/bin`) automatically.

If you set `PATH` explicitly in the `env` block, **Cursor does not expand `$PATH`** — provide the full value with your venv bin directory first.

### `No matching distribution found for deepcsim`

Your Python version is 3.14+. Use `--python /path/to/python3.13` with the install script, or set `python3.13` as your active interpreter.

### Shell script won't run on my MCP host

Point `command` at `.venv/bin/hotspottriage` directly and move `start-mcp-server` into `args`. See the **Direct binary variant** example in [Use with Cursor](#use-with-cursor) above.

### `scripts/run_hotspottriage_mcp.sh` — what does it do?

POSIX `sh` (not bash). It resolves the HotspotTriage checkout from the script's own location, prepends `.venv/bin` and common system directories to `PATH`, then `exec`s `hotspottriage start-mcp-server` with all passed arguments forwarded.