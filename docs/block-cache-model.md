# Block cache model (HotspotTriage)

Internal reference for how the **block-level analysis cache** is stored, written, reused, and invalidated. The bulk of this doc is **HotspotTriage** in this repository. An **[appendix](#appendix-serena-upstream-cache)** summarizes how [Serena](https://github.com/oraios/serena) implements its **SolidLSP document-symbol caches** and **agent memory** (different layer of the stack, useful for comparison).

## Why “Serena” appears in README

HotspotTriage borrows two **ideas** from Serena; neither is this pickle cache:

| Idea | In HotspotTriage |
|------|------------------|
| Layered YAML config | Merge order: code defaults → `~/.hotspottriage/config.yml` → `.hotspottriage/project.yml` → `project.local.yml` → `--config` → CLI flags |
| Isolated MCP runtime | Launcher pins `PATH` to the project venv so MCP sees predictable binaries (e.g. `pylint`) |

Block churn caching is implemented entirely in **`cache.py`**, **`block_churn.py`**, and **`stats.build_block_stats`**.

## On-disk layout

For a git repository root `<repo>`:

```text
<repo>/.hotspottriage/cache/
  blocks.pkl      # pickle: list of row dicts (Statistic fields + cache metadata)
  metadata.json   # generation timestamp, entry count, format version
```

Optional richer metadata (e.g. per-file blob tracking) is described in the main README under “Cache metadata and timestamps”; `cache._save_metadata` writes a **simple** `metadata.json` on each save (`generated_at`, `entry_count`, `version`).

Treat `.hotspottriage/` as **machine-local**; add it to `.gitignore` if you do not want cache committed.

## What one cached row contains

Each entry is a **full block row as a dict** (via `Statistic.as_dict()`), plus fields used only for cache logic:

| Field | Role |
|--------|------|
| `path` | `relative/path.py::symbol` |
| `churn` | Integer churn reused when valid |
| `_blob_sha` | Git blob SHA of the file at **HEAD** when the row was computed |
| `_start` / `_end` | Line range of the block in the file |

When a file’s HEAD blob and block spans match a complete cached snapshot, `build_block_stats` can **reuse full cached rows** for that file and skip Radon/smell/churn recompute; otherwise it runs the stale path. Similarity (DeepCSIM) is still computed across the **merged** block set for the run when enabled.

## When the cache is written

1. **Load** previous `blocks.pkl` (if any) into `prev_rows_list`.
2. Run block discovery, metrics, and `block_churn.compute_many` (see below).
3. Assemble new rows and merge **cache metadata** onto each dict.
4. **Merge with preserved rows** from the previous file for files **not** in the current analysis set (see “Scoped runs”).
5. **Atomically replace** `blocks.pkl` and refresh simple `metadata.json`.

Implementation anchors:

- `hotspottriage.cache.save_block_results`
- `hotspottriage.stats.build_block_stats` (tail: build `cache_rows`, merge, save)

## Reuse and invalidation (churn only)

### Blob SHA match (automatic invalidation)

For each requested block `(file_path, start, end)`:

1. Current blob for `file_path` is taken from **`git ls-tree -r HEAD`** (single call, map path → SHA).
2. The previous row for the same `(file_path, start, end)` is looked up.
3. If `cached_row["_blob_sha"] == current_blob_sha`, **churn is copied** from the cache.
4. Otherwise the block is **pending**; churn is computed with **`git log -L start,end:file`**.

Any edit that changes the file’s git blob at HEAD therefore **drops churn reuse** for blocks in that file. Renames or line shifts change `(path, start, end)` relative to the old index, which also forces fresh churn work for the new keys.

### Scoped / filtered runs

If analysis is limited to a subset of files (filters, etc.), **rows for files outside that subset are preserved** when rewriting `blocks.pkl`. That prevents a narrow run from wiping the whole-repo cache.

### Manual clear

MCP tool **`clear_cache(target)`** deletes `blocks.pkl` (and attempts to remove the cache directory). Use when you want a full cold churn recompute regardless of blob matches.

## MCP-related entry points

The stdio server process is **`hotspottriage start-mcp-server`** (Serena-style) or **`hotspottriage-mcp`**. Optional startup flag **`--default-target PATH_OR_URL`** applies when MCP tools pass an empty **`target`** (`analyze`, cache helpers, project **`init_config`**).

| Tool | Purpose |
|------|---------|
| `analyze` / `analyze_with_cache` | Block runs warm or use cache as part of analysis |
| `generate_cache` | Heavier cache generation path (see `cache_generator`) |
| `cache_status` | Inspect cache path, entry count, file size |
| `clear_cache` | Remove block cache file |

CLI block mode (`--blocks` / `granularity: block`) uses the same `build_block_stats` path and therefore the same cache semantics.

## Operational notes

- **Since / until**: Churn depends on git history windows; changing `since`/`until` does not change the cache key (blob + line range). Operators should treat cached churn as valid **only when blob matches**; if you change time windows and need strictly fresh churn, clear the cache or rely on blob changes.
- **Failures saving cache**: `build_block_stats` wraps the save in `try/except` and **ignores** save failures (analysis still returns).
- **clear_cache and metadata**: Clearing removes `blocks.pkl`; any extra files left under `cache/` may keep the directory from being removed—behavior is best-effort `rmdir`.

## Source map

| Module | Responsibility |
|--------|----------------|
| `cache.py` | Load/save `blocks.pkl`, simple `metadata.json` |
| `block_churn.py` | `file_blob_shas`, `compute_many` cache index, `git log -L` workers |
| `stats/` (`orchestration.py`, `cache_ops.py`, `pipeline.py`, …) | `build_block_stats`: partition cache vs stale, merge preserved rows, persist |
| `timestamps.py` | Richer metadata / staleness helpers used elsewhere (e.g. cache generator) |

---

## Appendix: Serena upstream cache

Serena’s code lives in [oraios/serena](https://github.com/oraios/serena). This section describes the **SolidLSP** side (Python package `solidlsp` inside that repo) and **memories**, not HotspotTriage.

### Pickle envelope (`solidlsp/util/cache.py`)

On-disk caches use a versioned wrapper:

- **Save:** `{"__cache_version": version, "obj": ...}`
- **Load:** Unpickle; if `__cache_version` is missing or does not equal the expected value, the **entire file is ignored** (logged, `None` returned).

Pickle I/O uses `sensai.util.pickle`.

### Two symbol caches (`solidlsp/ls.py`, `SolidLanguageServer`)

| Layer | In-memory shape | On-disk file |
|--------|------------------|--------------|
| Raw LSP `documentSymbol` | `dict[rel_path, (content_hash, raw_symbols)]` | `raw_document_symbols.pkl` |
| Processed “high-level” tree | `dict[rel_path, (content_hash, DocumentSymbols)]` | `document_symbols.pkl` |

- **Directory:** `{project_data_path}/cache/{language_id}/` (constant folder name `cache`).
- **Cache key:** relative file path (string).
- **Per-entry fingerprint:** `content_hash` = MD5 of file contents (`LSPFileBuffer.content_hash`), so a changed file drops symbol reuse for that path even if the pickle file loads.

Global constants (e.g. `RAW_DOCUMENT_SYMBOLS_CACHE_VERSION`, `DOCUMENT_SYMBOL_CACHE_VERSION`) and per-server **`cache_version_raw_document_symbols`** participate in the **pickle file** version; bumping them invalidates the **whole** persisted cache on the next load.

### Invalidation (three mechanisms)

1. **Whole pickle on load:** `load_cache(path, expected_version)` rejects the file if the stored `__cache_version` does not match. The expected version tuple can include **`_document_symbols_cache_fingerprint()`** (language-specific: build tags, clangd / compile_commands context, etc.). When that fingerprint changes, caches start empty—see upstream tests (e.g. Go build context, C++ clangd context).
2. **Per-file on lookup:** A hit requires `stored_hash ==` current buffer’s `content_hash`. Otherwise the server **re-queries the language server**.
3. **Empty LSP responses:** Raw symbol cache **does not persist** empty/`None` responses (avoids locking in “LS not ready” states, e.g. Lean before `lake build`).

Modified flags (`_raw_document_symbols_cache_is_modified`, `_document_symbols_cache_is_modified`) gate whether `save_cache()` rewrites the pickles.

### Open file buffer vs disk (`LSPFileBuffer`)

`contents` tracks `stat().st_mtime`; when the file changes on disk, the buffer reloads and `content_hash` updates, so symbol cache entries for that path go **stale** unless refreshed.

### Agent memories (not an LSP cache)

`MemoriesManager` (`serena/project.py`) stores **Markdown** under the project’s **`.serena/memories/`** and a **global** memories directory. This is **durable agent notes**, not derived LSP data and not keyed like symbol pickles.

### Comparison to HotspotTriage block cache

| Aspect | Serena / SolidLSP | HotspotTriage |
|--------|-------------------|---------------|
| What is cached | LSP document symbols (raw + processed) | Per-block **churn** (from `git log -L`) |
| Primary staleness key | MD5 **content hash** + optional LS **fingerprint** | Git **blob SHA** at `HEAD` + line range |
| On-disk layout | `{data}/cache/{lang}/*.pkl` | `<repo>/.hotspottriage/cache/blocks.pkl` |

---

*HotspotTriage section: aligned with this repo. Serena appendix: aligned with upstream `solidlsp` / `serena` as of the last review; re-check [oraios/serena](https://github.com/oraios/serena) if their cache semantics change.*
