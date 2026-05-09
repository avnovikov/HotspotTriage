# HotspotTriage Architecture

Detailed internal architecture covering data flow, caching layers, the
dashboard server, MCP integration, and known redundancies. Complement to
the top-level [README](README.md) and inline docstrings (per-function detail).

---

## 1. Analysis Pipeline

Every analysis — CLI, MCP tool, or dashboard-triggered — follows the same
five-stage pipeline.

```
Discovery → Filtering → Metrics Collection → Aggregation → Output
```

### 1.1 Discovery (`discovery.py`)

`git ls-files` enumerates tracked `.py` files. Remote URLs are cloned to a
temporary directory via `resolve_target()` (context manager that cleans up on
exit).

### 1.2 Filtering (`filtering.py`)

Glob patterns (AND semantics, `!` prefix for negation) plus directory-prefix
exclusion. `.gitignore` rules optionally applied to tracked files to catch
accidentally-committed ignored trees.

### 1.3 Metrics Collection

| Module              | Metric(s)                                             | Data source      |
|---------------------|-------------------------------------------------------|------------------|
| `complexity.py`     | `sloc`, `cyclomatic`, `halstead`, `maintainability`   | `radon` AST      |
| `churn.py`          | `churn`, `churn_per_sloc`, `decayed_churn*`           | `git log`        |
| `block_churn.py`    | Per-function churn via `git log -L`                   | `git log -L`     |
| `smell.py`          | `smell_count`, `smell_severity`, `smell_burden`       | Pylint + heuristics |
| `block_similarity.py` | `similarity_score`, `similarity_band`, `match_count` | DeepCSIM pairwise |

`complexity.compute_all(path)` handles full-file metrics.
`complexity.compute_for_source(snippet)` handles block snippets (no MI;
MI is copied from the parent file in `stats.build_block_stats`).

### 1.4 Aggregation (`stats.py`)

**File rows** (`build_stats`): one `Statistic` per file. `score` is the product
of `score_metrics` values (the "product recipe").

**Block rows** (`build_block_stats`):
1. Per-file `compute_all` + `extract_blocks` to get function/method AST nodes.
2. `block_churn.compute_many` (threaded, reuses churn from previous results via blob SHA match).
3. Per-block snippet metrics, smells, churn, decayed churn.
4. DeepCSIM similarity via `attach_similarity_to_rows`.
5. Z-scored `normalized_sloc` across all blocks in the run.
6. Initial `score` via product recipe; if `score_aggregation.enabled` (default),
   `score.compute_score` replaces it with a 0–1 weighted aggregate, setting
   `score_band` and `score_subscores`.

### 1.5 Output (`output.py`)

`statistic_to_output_dict` converts each `Statistic` to a plain dict.
When `metric_normalization` is configured, `normalize.normalize_record` appends
`norm_<metric>` columns. This is a **second normalization pass for display**
(the first is inside `score.compute_score` for the risk score itself).

---

## 2. `Statistic` Dataclass

Frozen dataclass carrying every metric so a single CSV/JSON dump can be
re-sorted later without rerunning.

```
path, sloc, normalized_sloc, cyclomatic, halstead, maintainability,
churn, churn_per_sloc, decayed_churn, decayed_churn_per_sloc,
smell_count, smell_severity, smell_burden, smells,
similarity_score, similarity_band, match_count,
score, score_band, score_subscores
```

Defined in `stats.py:46–70`.

---

## 3. Score Computation

### 3.1 Product Recipe (File + Block Fallback)

`stats._score(stat, metrics)`: multiply each metric value. Used for file-level
scoring and as the block fallback when `score_aggregation.enabled` is false.

### 3.2 Aggregated Risk Score (`score.py`, Block Only)

`compute_score` (called from `build_block_stats` when `score_aggregation.enabled`):

1. **Normalize** each raw metric → `[0, 1]` via `metric_normalization` config
   (methods: `identity`, `zscore`, `piecewise`, `inverse_piecewise`).
2. **Build burdens**: `complexity_burden`, `churn_burden`,
   `maintainability_burden`, `smell_burden`, `similarity_burden`.
3. **Weighted sum** with `final_weights` → `score` in `[0, 1]`.
4. **Band assignment** from `band_edges` / `band_names`.

`smell_burden` has a separate finalization path in
`stats._finalize_smell_burden`: within-run max normalization of counts × severity.

---

## 4. Configuration System

### 4.1 CLI Resolution (Layered, Last Wins)

```
DEFAULTS → ~/.hotspottriage/config.yml → <repo>/.hotspottriage/project.yml
         → project.local.yml → --config <PATH> → CLI flags
```

`config.load_config(target_path=repo)` merges all layers.
`config.validate(cfg)` enforces type/range constraints via focused private
helpers (`_validate_score_metrics`, `_validate_format_sort_granularity_log`,
`_validate_limit_and_block_workers`, etc.).

### 4.2 MCP Config Path

`mcp_server._build_analyze_config` starts from `DEFAULTS.copy()` + tool
argument overrides **only**. It does **not** call `load_config` for the target
repo. Project YAML files do not affect MCP `analyze`
unless settings are explicitly passed as tool arguments.

Editor-side MCP client config (e.g. Cursor **`.cursor/mcp.json`**: launcher paths, **`PATH`**, **`--default-target`**, git worktrees) is covered in **§6.1.2**.

### 4.3 Dashboard Config Overlay

The dashboard server maintains a `dashboard_config_patch.yml` file
(under `<cwd>/.hotspottriage/`). Only two top-level keys are accepted:

- `metric_normalization`
- `score_aggregation`

`GET /api/config` returns `_merged_snapshot()`: the base snapshot
deep-merged with the YAML patch. `POST /api/config/patch` validates
the merged result before writing.

**Caveat**: The merged snapshot drives the dashboard UI but does **not**
automatically rewire MCP `analyze` config. Block scores in published rows
still use the config built in `_build_analyze_config` (DEFAULTS + args).

---

## 5. Caching Layers

### 5.1 Disk Cache — `blocks.pkl` (Single Source of Truth)

| Aspect         | Detail |
|----------------|--------|
| **Path**       | `<repo>/.hotspottriage/cache/blocks.pkl` |
| **Content**    | `list[dict]` — one dict per function/method with **all** metrics, score, and cache metadata (`_blob_sha`, `_start`, `_end`) |
| **Invalidation** | Each row stores the file's blob SHA at the time of computation. On the next run, if the current blob SHA matches → churn is reused. If not → `git log -L` recomputes it. |
| **Write**      | `build_block_stats` in `stats.py` saves after assembling all rows |
| **Load (churn reuse)** | `build_block_stats` loads previous rows, passes to `block_churn.compute_many` which checks `_blob_sha` match |
| **Load (dashboard)** | `cache.load_block_results(repo)` deserializes the list for instant heatmap hydration |
| **Metadata**   | `metadata.json` alongside pickle: `generated_at`, `entry_count`, `version` |

One file, one structure. Each row is a function with its metrics **and** the
blob SHA needed for staleness detection. No separate churn cache.

`cache.py` exposes: `cache_path_for`, `save_block_results`, `load_block_results`,
`get_metadata`, `age_seconds`.

### 5.2 In-Memory: `_block_metrics_rows`

Live list of dict-ified `Statistic` rows, held by `DashboardServer`. Populated by:

- MCP `analyze` → `_publish_block_metrics_to_dashboard`
- Cache job completion → `publish_latest_block_metrics`
- `POST /api/cache/status` loads `blocks.pkl` directly from disk when
  cache exists and in-memory rows are empty (synchronous, sub-second)

Consumed by `GET /api/stats/heatmap` and `GET /api/stats/distribution`.
Protected by `_block_metrics_lock`.

### 5.4 Dashboard State — `dashboard_state.json`

| Aspect   | Detail |
|----------|--------|
| **Path** | `<cwd>/.hotspottriage/dashboard_state.json` (relative to process CWD, not analyzed repo) |
| **Content** | `last_target`, `last_filter` (combined include/exclude patterns), `last_include`, `last_exclude`, `last_score_metrics` (comma-separated recipe derived from the merged dashboard config snapshot—**not** from the UI), `recent_targets` (up to 15) |
| **Read/Write** | `GET/POST /api/cache/context`, `POST /api/cache/status`, `POST /api/cache/generate` |

### 5.5 Dashboard Config Patch — `dashboard_config_patch.yml`

See §4.3 above. YAML file, only `metric_normalization` and `score_aggregation`
keys, merged via `_config._deep_merge`.

---

## 6. MCP Server (`mcp_server.py`)

### 6.1 Lifecycle

`_mcp_lifespan` (async context manager):
1. Builds effective dashboard config from DEFAULTS + CLI overrides.
2. Creates `DashboardServer` (if enabled), stores as `_dashboard_server_instance`.
3. Starts dashboard on a free TCP port (daemon thread).
4. On exit, clears `_dashboard_server_instance`.

### 6.1.1 Startup argv (`main`)

Before `FastMCP.run`, `main()` parses leading argv with `argparse` (`add_help=False`,
`parse_known_args`): dashboard overrides (`--no-dashboard`, `--dashboard-port`,
`--dashboard-host`, `--open-browser`) and **`--default-target PATH_OR_URL`**.
Remaining argv is restored for the MCP runtime.

`--default-target` sets `_mcp_default_target`. MCP tools that take a repo **`target`**
(`analyze`, `generate_cache`, `cache_status`, `clear_cache`; project-scoped
`init_config`) resolve an empty or whitespace **`target`** via `_resolve_mcp_target`.

Repo **`scripts/run_hotspottriage_mcp.sh`** uses **`#!/bin/sh`**, discovers the
HotspotTriage checkout from the script path, prepends **`.venv/bin`** and standard
system dirs (**`/usr/bin`**, **`/bin`**, **`/usr/local/bin`**, **`/opt/homebrew/bin`**)
to **`PATH`** (MCP hosts such as Cursor often spawn with a stripped **`PATH`**, which
would otherwise make **`git`** unavailable), then **`exec`s `hotspottriage start-mcp-server "$@"`**. MCP **`args`** for that command
should therefore include only flags meant for **`start-mcp-server`** (not a second
`start-mcp-server` token). Clients that fail on shell wrappers should set **`command`**
to **`.venv/bin/hotspottriage`** and put **`start-mcp-server`** first in **`args`**,
merging the same system dirs into **`env.PATH`** if **`git`** is still missing.

### 6.1.2 Cursor workspaces and git worktrees

Editor MCP config (e.g. Cursor **`.cursor/mcp.json`**) is resolved relative to the **workspace root** the IDE opened. A **`git worktree`** adds a second checkout path on disk; launcher **`command`**, venv **`env.PATH`**, and **`--default-target`** must reference locations that exist from **that** workspace. Tool argument **`target`** names the **repository to analyze** (often the same path as the open project, not necessarily the HotspotTriage install).

Git allows only **one** linked worktree to hold a given branch; `git checkout main` fails locally when **`main`** is already checked out in another worktree (`git worktree list`). That limitation affects local CLI/git workflows and some **`gh pr merge`** invocations that update **`main`** in the current directory; it does not change MCP semantics. Prefer merging on GitHub or using the worktree that already has the base branch checked out.

### 6.2 Tool → Pipeline Mapping

| MCP Tool              | Pipeline                                           | Notes |
|-----------------------|----------------------------------------------------|-------|
| `analyze`             | `_analyze_repository` + `_initialize_repository`   | Block granularity only; **double** `build_block_stats` (see §9.1); publishes to dashboard |
| `generate_cache`      | `cache_generator.generate_full_cache` → `run_cached_block_analysis_dict` + `extract_class_method_structure` + `cache_status` | Inherits double-pass; optional progress callbacks surface current file in the dashboard job |
| `cache_status`        | `Cache(repo).get_metadata()` + `blocks.pkl` stat   | Lightweight, no analysis |
| `clear_cache`         | Deletes `blocks.pkl`                                | Leaves `metadata.json` |
| `init_config`         | `config.init_config` scaffolding                    | No analysis |

### 6.3 Dashboard Publishing

`_publish_block_metrics_to_dashboard`: when `granularity == "block"` and a
`DashboardServer` is running, pushes all `Statistic.as_dict()` rows to
`_block_metrics_rows`. Disk persistence is handled by `build_block_stats`
directly. The MCP tool calls `_publish_block_metrics_to_dashboard` with **full**
(unlimited) results.

---

## 7. Dashboard Server (`dashboard/server.py`)

### 7.1 Instance State

| Attribute                   | Purpose |
|-----------------------------|---------|
| `_base_snapshot`            | Deep copy of `to_dashboard_snapshot(...)` at construction |
| `_stats`                    | `StatsCollector` (wired but not actively updated by MCP tools) |
| `_log_handler`              | `MemoryLogHandler` ring buffer |
| `_host` / `_port`           | Bind address + chosen free port |
| `_started_at`               | `time.monotonic()` for uptime |
| `_cache_jobs` + lock        | Async cache job state |
| `_state_file` + lock        | `dashboard_state.json` |
| `_config_patch_path` + lock | `dashboard_config_patch.yml` |
| `_block_metrics_rows` + lock | Heatmap + histogram source |
| `_app`                      | FastAPI app |
| `_thread` / `_server`       | Uvicorn daemon thread + server handle |

All shared mutable state protected by dedicated `threading.Lock` instances.

### 7.2 API Endpoints

| Method | Path                       | Purpose |
|--------|----------------------------|---------|
| GET    | `/api/health`              | Uptime heartbeat |
| GET    | `/api/config`              | Merged base + YAML patch snapshot |
| POST   | `/api/config/patch`        | Persist normalization / score_aggregation overlay |
| GET    | `/api/stats/heatmap`       | Matrix rows for the heatmap table |
| GET    | `/api/stats/distribution`  | Histogram buckets for a named metric |
| GET    | `/api/cache/context`       | Read persisted dashboard state |
| POST   | `/api/cache/context`       | Save dashboard state (target, filter, score) |
| POST   | `/api/cache/status`        | Check `blocks.pkl` existence, entries, size; if cache exists and `_block_metrics_rows` is empty, load rows directly (synchronous, fast) |
| POST   | `/api/cache/generate`      | Spawn background cache job |
| GET    | `/api/cache/jobs/{job_id}` | Poll cache job progress |
| GET    | `/api/stats`               | `StatsCollector` snapshot |
| POST   | `/api/stats/clear`         | Reset `StatsCollector` |
| GET    | `/api/logs`                | Log messages (from index) |
| GET    | `/api/logs/stream`         | SSE log stream |
| GET    | `/api/stats/stream`        | SSE stats stream |
| GET    | `/dashboard/`              | Serve the single-page HTML dashboard |

### 7.3 Heatmap Data Flow

1. Rows land in `_block_metrics_rows` via one of:
   - MCP `analyze` → `_publish_block_metrics_to_dashboard`
   - Cache job completion → `publish_latest_block_metrics`
   - `POST /api/cache/status` → `cache.load_block_results(repo)` loads
     `blocks.pkl` directly (if cache exists and in-memory rows are empty).
     Synchronous pickle load, sub-second.

2. `_build_heatmap_rows` selects score + burden columns, splits
   `path::symbol` into `file` + `method`, sorts by file max score
   then method score, applies limit.

3. Frontend `refreshHeatmap` renders the green→yellow→orange→red
   color-coded table.

### 7.4 Path Normalization

`_normalize_cache_target` resolves relative paths (e.g. `./`, `../LexVox`)
to absolute paths via `Path.expanduser().resolve()`. Applied in
`set_cache_context`, `cache_status`, and `generate_cache`. Git URLs
(containing `://` or starting with `git@`) pass through unchanged.

---

## 8. Normalization (`normalize.py`)

Two distinct normalization surfaces exist:

### 8.1 Score Normalization (Inside `score.compute_score`)

Normalizes raw metrics → `[0, 1]` using `metric_normalization` config to
build burdens for the aggregated risk score. Happens once during
`build_block_stats`.

### 8.2 Output Normalization (Inside `output.statistic_to_output_dict`)

`normalize_record` adds `norm_<metric>` columns to the output dict for
display/export. Uses the same `normalize()` primitives but is a separate
pass that does **not** mutate `Statistic` fields.

### 8.3 Available Methods

| Method              | Behavior |
|---------------------|----------|
| `identity`          | Pass-through (clamped to `[0, 1]`) |
| `zscore`            | Requires population `mean`/`std`; maps to `[0, 1]` via sigmoid-like clamping |
| `piecewise`         | User-defined `[raw, norm]` breakpoint pairs, linearly interpolated |
| `inverse_piecewise` | Piecewise with `y` inverted (`1 - y`) so lower raw = higher normalized |

---

## 9. Known Redundancies and Caveats

### 9.1 Double `build_block_stats` in MCP `analyze`

MCP `analyze` runs `_analyze_repository` (which calls
`build_block_stats`) then `_initialize_repository` (which calls
`build_block_stats` again). The second pass mostly hits cache but still
repeats discovery, filtering, AST parsing, and complexity computation.

`generate_full_cache` inherits this double work since it calls
`analyze` internally.

### 9.2 ~~Heatmap Backfill Triggers Full Pipeline~~ (Resolved)

Previously `_publish_heatmap_rows_from_cache_best_effort` called
the full pipeline. Now heatmap hydration loads
`blocks.pkl` directly — a simple pickle deserialize with no pipeline.

### 9.3 ~~Separate Churn Cache and Results Cache~~ (Resolved)

Previously churn was cached as `dict[str, int]` (keyed by
`"{blob_sha}:{start}:{end}:{since}:{until}"`) in a separate structure from
the full results. Now a single `list[dict]` in `blocks.pkl` stores both
metrics and cache metadata (`_blob_sha`, `_start`, `_end`) on each row.
Staleness is checked by comparing the stored blob SHA against the current one.

### 9.4 Entry Count Sources Differ

Dashboard `POST /api/cache/status` uses `metadata.json` `entry_count`.
MCP `cache_status` counts `len(pickle dict)`. Usually aligned after `save()`
but can diverge if metadata is missing or stale.

### 9.5 `StatsCollector` Is Wired But Unused

`StatsCollector` is created and wired into the server but `record_call` is
never invoked by production MCP code — only in tests. It's infrastructure
for future instrumentation.

### 9.6 Two "Normalized" Concepts

`normalized_sloc` on `Statistic` is a within-batch z-score computed in
`build_block_stats`. `metric_normalization` in config drives per-metric
normalization in `score.py` and `output.py`. Different purposes, different
computation, easy to confuse.

### 9.7 MCP Config Ignores Project YAML

`_build_analyze_config` starts from `DEFAULTS.copy()` + tool args.
Project-level `project.yml` / `project.local.yml` are **not loaded**.
Dashboard patch YAML only drives the UI snapshot, not MCP analysis.

---

## 10. Thread Safety Model

| Resource               | Lock                         | Accessed from |
|------------------------|------------------------------|---------------|
| `_cache_jobs`          | `_cache_jobs_lock`           | HTTP handlers, background cache threads |
| `_block_metrics_rows`  | `_block_metrics_lock`        | HTTP handlers, MCP publish, cache job callback |
| `dashboard_state.json` | `_state_lock`                | HTTP handlers (context, status, generate) |
| `dashboard_config_patch.yml` | `_patch_lock`          | HTTP handlers (get/patch config) |
| `MemoryLogHandler`     | Internal `_lock`             | Logger threads, HTTP handlers |
| `StatsCollector`       | Internal `_lock`             | HTTP handlers, SSE stream |

The dashboard server runs in a daemon thread (`_thread`). Uvicorn handles
concurrent HTTP requests via asyncio; route handlers acquire locks
synchronously. Background cache jobs run in separate daemon threads.

---

## 11. Entry Points

| Command                | Module                 | What it does |
|------------------------|------------------------|--------------|
| `hotspottriage <repo>` | `cli.py`               | CLI analysis (file or block) |
| `hotspottriage start-mcp-server` | `cli.py` → `mcp_server.py:main` | FastMCP server on stdio + optional dashboard (Serena-style) |
| `hotspottriage-mcp`    | `mcp_server.py:main`   | Same as `start-mcp-server` (direct console script alias) |
| `hotspottriage-cache`  | `cache_generator.py:main` | Comprehensive cache generation |

All registered as `[project.scripts]` in `pyproject.toml`.

---

## 12. Dashboard UI (`dashboard/html.py`)

Single-file HTML/CSS/JS served at `/dashboard/`. Three views via hash routing:

| Route       | Content |
|-------------|---------|
| `#overview` | Project path, granularity; labeled cache fields (repository root, include/exclude patterns); **Save cache settings**; check/generate cache; log viewer |
| `#heatmap`  | Read-only **repository root** (copied from Overview); limit control; **Update Heatmap**; color-coded matrix |
| `#config`   | Normalization breakpoint editors; weight sliders; save/refresh config |

The Heatmap tab shows the same repo path as Overview via `syncHeatmapRepoDisplay()` (not editable there).
Cache context is persisted when the user clicks **Save cache settings** or when **Check Cache** / **Generate Cache** runs (best-effort save before the action).
