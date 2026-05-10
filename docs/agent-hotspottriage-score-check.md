# HotspotTriage score check before edits

Use this when an AI agent edits this codebase (formerly mirrored as a Cursor rule).

Before changing existing code, run a HotspotTriage MCP score check for the function or block you plan to edit.

## Requirements (contract)

These behaviors are **enforced in tests**; keep them when changing MCP, `explain`, `stats`, or CLI JSON output.

1. **Compact-first triage.** Default MCP **`analyze`** uses **`compact=true`**. Agents should call **`analyze`** that way first, then **`compact=false`** only when compact rows are insufficient (full **`path`**, all scalar metrics, **`score_subscores`**, **`score_explanation`**, **`score_narrative`**, optional **`norm_*`**).
2. **Compact row shape.** With **`compact=true`**, each result row is only: **`function`**, **`score`**, **`risk_band`**, **`proposed_model`**, **`score_driver`**, **`rationale`**. There is **no** per-row **`score_explanation`**, **`score_narrative`**, or full metric dict in that mode.
3. **No `raw` in `score_explanation`.** Wherever **`score_explanation`** appears (MCP full **`analyze`**, CLI **`--blocks`** JSON/CSV, dashboard payloads, `Statistic` rebuilt from dicts), each explanation object must **not** include a **`raw`** field. Use **`normalized`** (and burdens / weights) only. Legacy cache or hand-built dicts that still carry **`raw`** are stripped when statistics are loaded from dicts (`sanitize_score_explanation_entries`).

## MCP `analyze` `filter` parameter (paths and globs)

Tokens are comma-separated, repo-relative POSIX paths. Matching depends on **what** you pass:

| Situation | Semantics | Example |
|-----------|------------|---------|
| **Two or more tokens**, each a **literal path** (no `* ? [ ] { }`) | **OR** — file kept if it equals **any** token | `src/a.py,src/b.py` |
| **One token** (literal or glob) | **AND** glob mode (with default filter) | `src/hotspottriage/stats.py` |
| **Any glob** in any token, or **mixed** literal + glob | **AND** across all tokens | `src/**,!**/test_*` |
| **Literal + glob** in one filter string | **AND** (not “file A or glob B”) — easy to get **empty** results | Prefer two `analyze` calls or a single inclusive glob |

**Not the same as the CLI:** `hotspottriage … --filter` and `hotspottriage-cache --filter` always use **AND** glob mode (no literal-path OR shortcut). Only the MCP **`analyze`** tool applies `_build_repo_keep_predicate` in `mcp_server.py`, which implements the OR shortcut above.

## Workflow

1. Identify the exact function or method you plan to modify.
2. **Triage first:** call HotspotTriage MCP **`analyze`** with **`compact=true`** (the default) so you get small rows only: **`function`**, **`score`**, **`risk_band`**, **`proposed_model`**, **`score_driver`**, and **`rationale`** (one-line natural language: main driver, top normalized causes, optional “Second: …”). Use block-level + cache; pass **`target`**, or leave it empty when the MCP server was started with **`--default-target`** pointing at that repo. Call again with **`compact=false`** only when compact rows are not enough: full row with **`path`** (`file.py::symbol`), every metric, **`score_band`**, **`score_subscores`** (when score aggregation is enabled), **`score_explanation`** (drivers, burdens, **`normalized`** inputs, weights—no raw counters), **`score_narrative`**, optional **`norm_*`**, and **`proposed_model`**.
3. Locate the matching row (`path::symbol` ↔ **`path`** in full mode, or **`function`** in compact mode) and capture:
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
