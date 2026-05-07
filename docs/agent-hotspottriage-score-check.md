# HotspotTriage score check before edits

Use this when an AI agent edits this codebase (formerly mirrored as a Cursor rule).

Before changing existing code, run a HotspotTriage MCP score check for the function or block you plan to edit.

## Workflow

1. Identify the exact function or method you plan to modify.
2. Use HotspotTriage MCP **`analyze`** (block-level + cache) for the target repo/path; pass **`compact=false`** when you need full metric rows.
3. Locate the matching block row (`path::symbol`) and capture:
   - `score`
   - `score_band`
   - `score_subscores` (if present)
4. Use that result to guide edit priority and risk framing in your plan or notes.

## Minimum reporting in planning notes

- Target symbol/path
- Current score and band
- One-line rationale based on score/subscores

## Example

- Target: `src/module.py::MyClass.process`
- Score: `0.74` (`high`)
- Rationale: high churn burden and maintainability burden; keep change minimal and add focused tests.
