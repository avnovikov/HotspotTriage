## Learned User Preferences
- **Always create or switch to a git branch before starting any implementation work** in this repo (do not start edits on `main`/`master` unless the user explicitly says so). For a GitHub issue, use that issue’s branch; otherwise use a short-lived `feature/…`, `fix/…`, or `chore/…` branch.
- When requested to close an issue, complete the full lifecycle in one pass: run relevant tests, commit, create a PR, then close the issue.

## Learned Workspace Facts

### HotspotTriage MCP composite score — branch vs `main` (`mcp_server.py`)

To compare **composite `score` only** across branches, call MCP **`analyze`** twice (there is no git-ref parameter): once with `target=<repo>` on the feature branch, once with `target=<second checkout>` on `main` (e.g. a sibling **`git worktree add ../<name> main`**). Use the same options (e.g. `compact=false`, `similarity=false`, `filter=src/hotspottriage/mcp_server.py`) and compare raw **`score`** (not `norm_*`, which is repo-relative).

Recorded deltas for the MCP config-loading change (`issue-52` / proposed models): **`_build_analyze_config`** ~**0.651 → 0.697** (**+0.046**); **`run_cached_block_analysis_dict`** ~**0.581 → 0.593** (**+0.012**). Primary hotspot movement is **`_build_analyze_config`**.

### Cursor MCP + git worktrees

Cursor resolves **`.cursor/mcp.json`** from the **opened workspace folder**. After **`git worktree add`**, each checkout is a different path: **`command`**, **`env.PATH`**, and **`--default-target`** must match **that** tree (or a deliberate shared install). Stale paths cause wrong **`target`** repos or missing **`git`** when the host starts MCP with a thin **`PATH`**.

Git allows only one linked worktree to check out a given branch; **`git checkout main`** fails here if **`main`** is already checked out elsewhere (**`git worktree list`**). Some local **`gh pr merge`** flows that expect **`main`** in the current directory hit the same constraint—use the GitHub UI/API or the worktree that already has the base branch.
