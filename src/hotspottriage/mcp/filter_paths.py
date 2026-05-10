"""MCP ``analyze`` filter path tokens (literal OR list vs glob AND)."""
from __future__ import annotations

from typing import Any

from hotspottriage import filtering


def is_literal_filter_path(pattern: str) -> bool:
    """Return True when *pattern* looks like a concrete path, not a glob."""
    token = pattern.strip()
    if not token or token.startswith("!"):
        return False
    return not any(ch in token for ch in "*?[]{}")


def normalize_filter_path(path: str) -> str:
    """Normalize a filter path to POSIX relative form for exact matching."""
    return filtering.normalize_filter_pattern(path)


def effective_mcp_filter_patterns(cfg: dict[str, Any]) -> list[str]:
    """Return the filter token list actually used by the MCP repo keep predicate."""
    raw_patterns = [p.strip() for p in cfg.get("filter", []) if p and str(p).strip()]
    use_literal_list = len(raw_patterns) > 1 and all(
        is_literal_filter_path(p) for p in raw_patterns
    )
    if use_literal_list:
        return list(raw_patterns)
    patterns = list(raw_patterns)
    if not cfg.get("no_default_filter", False):
        df = cfg.get("default_filter")
        if isinstance(df, str) and df.strip():
            patterns.append(df.strip())
    return patterns
