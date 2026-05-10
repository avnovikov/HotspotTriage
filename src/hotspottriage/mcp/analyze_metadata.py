"""MCP ``analyze`` response ``metadata`` (provenance, counts, config fingerprint)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hotspottriage import stats
from hotspottriage.mcp.block_row_utils import normal_block_stat_count
from hotspottriage.mcp.config_fingerprint import config_fingerprint
from hotspottriage.mcp.filter_paths import effective_mcp_filter_patterns
from hotspottriage.mcp.git import git_live_head_and_branch, git_short_object_name


def build_analyze_metadata(
    cfg: dict[str, Any],
    analysis_root: str,
    results_full: list[stats.Statistic],
    results_limited: list[stats.Statistic],
    *,
    git_repo: Path | None = None,
    snapshot_commit_full: str | None = None,
    analyzed_at: str | None = None,
) -> dict[str, Any]:
    """Build the top-level ``metadata`` object for an MCP analyze payload."""
    at = analyzed_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    git_head: str | None = None
    git_branch: str | None = None
    if git_repo is not None and snapshot_commit_full:
        git_head = git_short_object_name(git_repo, snapshot_commit_full)
        git_branch = "snapshot"
    elif git_repo is not None:
        git_head, git_branch = git_live_head_and_branch(git_repo)

    row_count = normal_block_stat_count(results_full)
    truncated = normal_block_stat_count(results_limited) < row_count

    return {
        "git_head": git_head,
        "git_branch": git_branch,
        "analyzed_at": at,
        "target": analysis_root,
        "filter_applied": effective_mcp_filter_patterns(cfg),
        "row_count": row_count,
        "truncated": truncated,
        "config_fingerprint": config_fingerprint(cfg),
    }
