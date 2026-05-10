# HotspotTriage score check before edits

Use this when an AI agent edits this codebase (formerly mirrored as a Cursor rule).

Before changing existing code, run a HotspotTriage MCP score check for the function or block you plan to edit.

## Requirements (contract)

These behaviors are **enforced in tests**; keep them when changing MCP, `explain`, `stats`, or CLI JSON output.

1. **Compact-first triage.** Default MCP **`analyze`** uses **`compact=true`**. Agents should call **`analyze`** that way first, then **`compact=false`** only when compact rows are insufficient (full **`path`**, all scalar metrics, **`score_subscores`**, **`score_explanation`**, **`score_narrative`**, optional **`norm_*`**).
2. **Compact row shape.** With **`compact=true`**, each result row is only: **`file`**, **`function`**, **`score`**, **`risk_band`**, **`proposed_model`**, **`score_driver`**, **`rationale`**. There is **no** per-row **`score_explanation`**, **`score_narrative`**, or full metric dict in that mode.
3. **Similarity default vs `filter`.** When **`similarity`** is omitted on MCP **`analyze`**, DeepCSIM is **off** if **`filter`** is set (scoped runs), **on** for whole-repo runs. Pass **`similarity=true`** explicitly for clone detection on a filtered path.
4. **No `raw` in `score_explanation`.** Wherever **`score_explanation`** appears (MCP full **`analyze`**, CLI **`--blocks`** JSON/CSV, dashboard payloads, `Statistic` rebuilt from dicts), each explanation object must **not** include a **`raw`** field. Use **`normalized`** (and burdens / weights) only. Legacy cache or hand-built dicts that still carry **`raw`** are stripped when statistics are loaded from dicts (`sanitize_score_explanation_entries`).
5. **`include_summary` default.** With **`include_summary=false`** (the default), MCP **`analyze`** must **not** include a **`summary`** key. With **`include_summary=true`**, **`summary`** aggregates use the **full** pre-**`limit`** block set so **`limit`** only trims **`results`**, not the overview.
6. **Structured MCP tool errors.** On failure, affected tools return JSON with a top-level **`error`** object **`{"code", "message", "details"}`** (not a plain string). Branch on **`error.code`**; treat **`message`** as human-readable only. Success payloads are unchanged (e.g. **`analyze`** with **`metadata`** / **`results`**, **`cache_status`** with **`status`**: **`ok`** / **`empty`**, **`init_config`** with **`status`**: **`success`**).

## MCP tool errors (structured envelope)

When an MCP tool in `mcp_server.py` fails, the response is a JSON object:

```json
{
  "error": {
    "code": "SNAPSHOT_NOT_FOUND",
    "message": "…",
    "details": {}
  }
}
```

- **`code`**: stable category for agents (prefer this over parsing **`message`**).
- **`message`**: end-user / log text; wording may evolve.
- **`details`**: optional context (paths, **`errno`**, git **`returncode`**, tool name, etc.); always an object, often `{}`.

**Tools that use this shape on failure:** **`analyze`**, **`generate_cache`**, **`cache_status`**, **`clear_cache`**, **`init_config`**, and the cache-backed path behind **`analyze`** (same envelope from **`_run_analyze_cached`**). **`cache_status`** / **`clear_cache`** still use **`status`** for non-error outcomes (**`ok`**, **`empty`**, **`success`**).

**Typical `code` values (non-exhaustive):** **`INVALID_TARGET`** (empty target without **`--default-target`**, remote URL where a local path is required), **`TARGET_NOT_FOUND`** (path not a repo / not found), **`INVALID_FILTER`**, **`CONFIG_VALIDATION`** (includes config init **`FileExistsError`** “already exists”), **`GIT_ERROR`**, **`CACHE_ERROR`**, **`INTERNAL`**, **`INVALID_ARGUMENT`** (e.g. **`after_sha`** without **`before_sha`**), **`SNAPSHOT_NOT_FOUND`** (revision snapshot never recorded for that SHA at that repo).

## MCP `analyze` `filter` parameter (paths and globs)

Tokens are comma-separated, repo-relative POSIX paths. Matching depends on **what** you pass:

| Situation | Semantics | Example |
|-----------|------------|---------|
| **Two or more tokens**, each a **literal path** (no `* ? [ ] { }`) | **OR** — file kept if it equals **any** token | `src/a.py,src/b.py` |
| **One token** (literal or glob) | **AND** glob mode (with default filter) | `src/hotspottriage/stats.py` |
| **Any glob** in any token, or **mixed** literal + glob | **AND** across all tokens | `src/**,!**/test_*` |
| **Literal + glob** in one filter string | **AND** (not “file A or glob B”) — easy to get **empty** results | Prefer two `analyze` calls or a single inclusive glob |

**Not the same as the CLI:** `hotspottriage … --filter` and `hotspottriage-cache --filter` always use **AND** glob mode (no literal-path OR shortcut). Only the MCP **`analyze`** tool applies `_build_repo_keep_predicate` in `mcp_server.py`, which implements the OR shortcut above.

## MCP `analyze` response `metadata`

Successful JSON includes a top-level **`metadata`** object for provenance and
repeatability: **`git_head`** (short SHA), **`git_branch`** (current branch,
**`detached`**, or **`snapshot`** when **`results`** are served only from the
**`after_sha`** revision cache), **`analyzed_at`** (UTC, `Z` suffix),
**`target`**, **`filter_applied`** (effective filter list after MCP OR/glob
rules), **`row_count`** (non-aggregate block rows before the response
**`limit`**), **`truncated`**, and **`config_fingerprint`** (SHA-256 digest of the
merged config for the run). **`results`** and **`cache`** shapes are unchanged;
**`head_sha`** and **`deltas`** remain optional sibling keys as in the section
below.

## MCP `analyze` optional `include_summary`

When **`include_summary=true`**, the response adds a top-level **`summary`**
object with **`block_count`**, **`high_risk_count`**, **`critical_risk_count`**,
**`sum_cyclomatic`**, **`sum_sloc`**, **`max_cyclomatic`** and **`max_score`**
(each ``{"path": "file.py::symbol", "value": …}``, or ``null`` when there are no
blocks), and **`mean_score`**. Aggregates are computed from the **full**
pre-**`limit`** block set so a small **`limit`** on **`results`** does not shrink
the overview. Default **`include_summary=false`** omits **`summary`** so
existing callers see no change.

## MCP `analyze` revision snapshots (`head_sha`, `before_sha`, `after_sha`)

On a **local** `target`, each successful **`analyze`** records a snapshot under
`<repo>/.hotspottriage/cache/revisions.pkl` and returns **`head_sha`** (the
recorded commit). To diff two commits **without** HotspotTriage checking out
another revision:

1. Run **`analyze`** at the older checkout → save **`head_sha`** as `H1`.
2. Run **`analyze`** at the newer checkout → save **`head_sha`** as `H2`.
3. Call **`analyze(target, before_sha=H1, after_sha=H2, …)`** with the same
   filter/options as needed → **`results`** reflect `H2`, **`deltas`** compare
   `H2` vs `H1`, **`head_sha`** is `H2`.

Alternatively, **`analyze(target, before_sha=H1, …)`** (only `before_sha`)
runs a **live** analysis at the current `HEAD`, records it, and adds **`deltas`**
vs the cached `H1` snapshot.

If a SHA was never recorded at that repo path, the tool returns a structured
error with **`code`**: **`SNAPSHOT_NOT_FOUND`** and a **`message`** mentioning
**no cached snapshot** (run **`analyze`** at that commit first).

## Workflow

1. Identify the exact function or method you plan to modify.
2. **Triage first:** call HotspotTriage MCP **`analyze`** with **`compact=true`** (the default) so you get small rows only: **`file`**, **`function`**, **`score`**, **`risk_band`**, **`proposed_model`**, **`score_driver`**, and **`rationale`** (one-line natural language: main driver, top normalized causes, optional “Second: …”). Use block-level + cache; pass **`target`**, or leave it empty when the MCP server was started with **`--default-target`** pointing at that repo. Call again with **`compact=false`** only when compact rows are not enough: full row with **`path`** (`file.py::symbol`), every metric, **`score_band`**, **`score_subscores`** (when score aggregation is enabled), **`score_explanation`** (drivers, burdens, **`normalized`** inputs, weights—no raw counters), **`score_narrative`**, optional **`norm_*`**, and **`proposed_model`**.
3. Locate the matching row (`path::symbol` ↔ **`path`** in full mode, or **`file`** + **`function`** in compact mode) and capture:
   - **`score`**
   - Band: **`risk_band`** (compact) or **`score_band`** (full)
   - **`score_subscores`** when you used **`compact=false`** and aggregation is on (otherwise omit or `{}`)
   - **`proposed_model`** when set (config **`proposed_models`** maps bands to suggested model names)
   - **`score_driver`** and **`rationale`** when you used **`compact=true`**
4. Use that snapshot for edit priority, risk framing, and model routing in your plan or notes.

## Minimum reporting in planning notes

- Target symbol/path (`path` or `function` from the row)
- **`score`** and band (**`risk_band`** or **`score_band`**)
- **`score_subscores`** when you used full rows and they’re non-empty
- **`proposed_model`** when present
- One-line rationale tied to those fields

## Example

- Target: `src/module.py::MyClass.process` (full row **`path`**); compact row **`function`**: `MyClass.process`
- Score: `0.74`, band: **`high`** (`risk_band` / `score_band`)
- **`proposed_model`**: e.g. strongest tier from config (if configured)
- Rationale: high churn and maintainability burden in **`score_subscores`**; keep change minimal and add focused tests.
