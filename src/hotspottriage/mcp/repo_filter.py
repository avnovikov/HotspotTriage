"""MCP analyze: build a tracked-file predicate from config ``filter`` tokens."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from hotspottriage import filtering
from hotspottriage.mcp.filter_paths import is_literal_filter_path, normalize_filter_path


def build_repo_keep_predicate(repo: Path, cfg: dict[str, Any]) -> Callable[[str], bool]:
    """Build tracked-path predicate with MCP-friendly multi-file filter handling."""
    raw_patterns = [p.strip() for p in cfg["filter"] if p and p.strip()]
    use_literal_list = len(raw_patterns) > 1 and all(
        is_literal_filter_path(p) for p in raw_patterns
    )

    if use_literal_list:
        allowed_paths = {normalize_filter_path(p) for p in raw_patterns}

        def glob_keep(rel_posix: str) -> bool:
            return normalize_filter_path(rel_posix) in allowed_paths

    else:
        patterns = list(cfg["filter"])
        if not cfg["no_default_filter"]:
            patterns.append(cfg["default_filter"])
        glob_keep = filtering.make_filter(patterns)

    return filtering.make_tracked_path_predicate(
        repo,
        glob_keep=glob_keep,
        ignore_directories=cfg["ignore_directories"],
        respect_gitignore=cfg["respect_gitignore"],
    )
