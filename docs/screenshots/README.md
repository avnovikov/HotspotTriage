# Screenshots for GitHub

GitHub renders images in [`README.md`](../../README.md) when you use **paths relative to the repository root** (for example `docs/screenshots/dashboard-overview.png`). Commit the PNGs in this folder; no external image host is required. Assets here are meant to be **actual captures** of the running app unless noted otherwise.

## Updating

When the dashboard UI changes enough that the README should reflect it:

1. Run the MCP server with the dashboard open, for example:  
   `uv run hotspottriage start-mcp-server --open-browser`  
   optional default repo for tools: add `--default-target /absolute/path/to/repo`.
2. Capture the browser viewport (or window) and export as PNG.
3. Replace the files below **in place** (same filenames so [`README.md`](../../README.md) keeps working).

## Files referenced from the main README

| File | Purpose |
|------|---------|
| `dashboard-overview.png` | Authentic capture of the bundled dashboard (**Overview** route) |

Optional extras: `heatmap.png`, `mcp-cursor.png`, etc.—add under this folder and reference them from [`README.md`](../../README.md) with the same relative-path pattern.
