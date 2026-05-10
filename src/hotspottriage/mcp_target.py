"""Resolve MCP ``target`` tool argument against optional ``--default-target``."""
from __future__ import annotations


def resolve_mcp_target(target: str, *, default_target: str | None) -> str:
    """Resolve repo path/URL: explicit *target*, else *default_target*, else error."""
    t = target.strip() if isinstance(target, str) else ""
    if t:
        return t
    if default_target:
        return default_target
    raise ValueError(
        "MCP tool requires a non-empty target (local git repo path or remote URL), "
        "or start the server with --default-target PATH_OR_URL"
    )
