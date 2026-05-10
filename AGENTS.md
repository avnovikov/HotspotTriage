## Learned User Preferences
- **Always create or switch to a git branch before starting any implementation work** in this repo (do not start edits on `main`/`master` unless the user explicitly says so). For a GitHub issue, use that issue’s branch; otherwise use a short-lived `feature/…`, `fix/…`, or `chore/…` branch.
- When requested to close an issue, complete the full lifecycle in one pass: run relevant tests, commit, create a PR, then close the issue.

## Learned Workspace Facts

### MCP `analyze` triage and `score_explanation` (agent contract)

- **Triage order:** Call MCP **`analyze`** with **`compact=true`** first (it is the default). Use **`compact=false`** only when you need full block rows (`path`, all metrics, **`score_subscores`**, **`score_explanation`**, **`score_narrative`**, optional **`norm_*`**). Same guidance is spelled out in [docs/agent-hotspottriage-score-check.md](docs/agent-hotspottriage-score-check.md).
- **Compact rows:** Only **`function`**, **`score`**, **`risk_band`**, **`proposed_model`**, **`score_driver`**, and **`rationale`**—no embedded **`score_explanation`** or long narrative in each compact row.
- **No `raw` in explanations:** **`score_explanation`** list items never expose a **`raw`** object (normalized inputs and weights only). Persisted rows with legacy **`raw`** are sanitized when deserialized.

### MCP `analyze` `filter` (literal OR vs glob AND)

Comma-separated `filter` on MCP **`analyze`**: if there are **two or more** tokens and **every** token is a **literal path** (no `* ? [ ] { }`), paths are matched with **OR** (include if the file equals any token). Otherwise tokens are gitignore-style **AND** globs (`!` negates). The **`hotspottriage`** / **`hotspottriage-cache`** CLIs always use **AND** globs only. Details: [docs/agent-hotspottriage-score-check.md](docs/agent-hotspottriage-score-check.md).

### HotspotTriage MCP vs CLI analyze config

CLI analyze without `--no-config` uses the same stack as MCP local `analyze` (`use_global=False`, project YAML, `dashboard_config_patch.yml`, then CLI flags or MCP tool args). Repository tests pass `--no-config` so a developer `~/.hotspottriage/config.yml` cannot change assertions.

### HotspotTriage MCP composite score — branch vs `main` (`mcp_server.py`)

**Revision snapshots (preferred):** On a **local** repo, run **`analyze`** at the first checkout and save **`head_sha`**, check out the other branch, run **`analyze`** again, then call **`analyze(..., before_sha=<older head_sha>, after_sha=<newer head_sha>)`** for a cached-only diff (no extra checkout inside HotspotTriage). Compare raw **`score`** (not `norm_*`, which is repo-relative).

**Two checkouts:** You can still call **`analyze`** twice with different **`target`** paths (e.g. a sibling **`git worktree add ../<name> main`**) and compare raw **`score`** manually if you do not have recorded **`head_sha`** values.

Recorded deltas for the MCP config-loading change (`issue-52` / proposed models): **`_build_analyze_config`** ~**0.651 → 0.697** (**+0.046**); **`run_cached_block_analysis_dict`** ~**0.581 → 0.593** (**+0.012**). Primary hotspot movement is **`_build_analyze_config`**.

### Cursor MCP + git worktrees

Cursor resolves **`.cursor/mcp.json`** from the **opened workspace folder**. After **`git worktree add`**, each checkout is a different path: **`command`**, **`env.PATH`**, and **`--default-target`** must match **that** tree (or a deliberate shared install). Stale paths cause wrong **`target`** repos or missing **`git`** when the host starts MCP with a thin **`PATH`**.

Git allows only one linked worktree to check out a given branch; **`git checkout main`** fails here if **`main`** is already checked out elsewhere (**`git worktree list`**). Some local **`gh pr merge`** flows that expect **`main`** in the current directory hit the same constraint—use the GitHub UI/API or the worktree that already has the base branch.
