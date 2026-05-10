"""Resolve MCP tool targets to local repo paths (reject remote git URLs)."""

from __future__ import annotations

from pathlib import Path

from hotspottriage import discovery
from hotspottriage.mcp.errors import mcp_tool_error
from hotspottriage.path_utils import resolve_local_repo_path


def local_repo_path_or_error(
    resolved_target: str,
    *,
    tool: str,
    remote_message: str,
) -> Path | str:
    """Return a resolved local :class:`Path`, or a JSON error string for remote URLs."""
    raw = resolved_target.strip()
    if discovery.is_git_url(raw):
        return mcp_tool_error(
            "INVALID_TARGET",
            remote_message,
            details={"tool": tool, "reason": "remote_url_not_supported"},
        )
    return resolve_local_repo_path(raw)
