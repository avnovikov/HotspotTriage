# Screenshots for GitHub

GitHub renders images in `README.md` when you use **paths relative to the repository root** (for example `docs/screenshots/dashboard-overview.png`). Commit the image files; no hosting service is required.

## Updating

1. Run the MCP server with the dashboard, for example:  
   `uv run hotspottriage start-mcp-server --open-browser`
2. Capture the browser window (or viewport) and export as PNG.
3. Overwrite the files listed below (keep the same filenames so `README.md` stays valid).

## Files referenced from the main README

| File | Purpose |
|------|---------|
| `dashboard-overview.png` | Web dashboard (overview / typical layout) |

Optional extras you can add later: `heatmap.png`, `mcp-cursor.png`, etc.—then reference them from `README.md` with the same relative-path pattern.
