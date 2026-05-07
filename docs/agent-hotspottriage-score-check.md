# HotspotTriage score check before edits

Use this when an AI agent edits this codebase (formerly mirrored as a Cursor rule).

Before changing existing code, run a HotspotTriage MCP score check for the function or block you plan to edit.

## Workflow

1. Identify the exact function or method you plan to modify.
2. Use HotspotTriage MCP **`analyze`** (block-level + cache) for the target repo/path. Default **`compact=true`** returns small rows: **`function`**, **`score`**, **`risk_band`**, **`proposed_model`**. Pass **`compact=false`** when you need the full row: **`path`** (`file.py::symbol`), every metric, **`score_band`**, **`score_subscores`** (when score aggregation is enabled), optional **`norm_*`**, and **`proposed_model`**.
3. Locate the matching row (`path::symbol` ↔ **`path`** in full mode, or **`function`** in compact mode) and capture:
   - **`score`**
   - Band: **`risk_band`** (compact) or **`score_band`** (full)
   - **`score_subscores`** when you used **`compact=false`** and aggregation is on (otherwise omit or `{}`)
   - **`proposed_model`** when set (config **`proposed_models`** maps bands to suggested model names)
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
