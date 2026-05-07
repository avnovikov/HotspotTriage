## Learned User Preferences
- Before implementing issue work, create or switch to the dedicated issue branch first.
- When requested to close an issue, complete the full lifecycle in one pass: run relevant tests, commit, create a PR, then close the issue.

## Learned Workspace Facts

### HotspotTriage MCP composite score — branch vs `main` (`mcp_server.py`)

To compare **composite `score` only** across branches, call MCP **`analyze`** twice (there is no git-ref parameter): once with `target=<repo>` on the feature branch, once with `target=<second checkout>` on `main` (e.g. a sibling **`git worktree add ../<name> main`**). Use the same options (e.g. `compact=false`, `similarity=false`, `filter=src/hotspottriage/mcp_server.py`) and compare raw **`score`** (not `norm_*`, which is repo-relative).

Recorded deltas for the MCP config-loading change (`issue-52` / proposed models): **`_build_analyze_config`** ~**0.651 → 0.697** (**+0.046**); **`run_cached_block_analysis_dict`** ~**0.581 → 0.593** (**+0.012**). Primary hotspot movement is **`_build_analyze_config`**.
