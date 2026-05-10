"""Validate and resolve MCP ``analyze`` tool arguments into a typed context."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hotspottriage import discovery
from hotspottriage.mcp.analyze_config import (
    build_analyze_config,
    effective_similarity_enabled_for_mcp_analyze,
)
from hotspottriage.path_utils import resolve_local_repo_path


@dataclass(frozen=True, slots=True)
class AnalyzeInputs:
    """Resolved, validated context for a single MCP ``analyze`` call."""

    analysis_root: str
    local_repo: Path | None
    cfg: dict[str, Any]
    before_sha: str | None
    after_sha: str | None
    compact: bool
    include_summary: bool


def resolve_analyze_inputs(
    target: str,
    *,
    path_filter: str | None = None,
    score_metrics: str | None = None,
    limit: int | None = None,
    since: str | None = None,
    until: str | None = None,
    respect_gitignore: bool = True,
    ignore_dir: str | None = None,
    similarity: bool | None = None,
    compact: bool = True,
    sort: str = "score",
    config_overrides: dict[str, Any] | None = None,
    before_sha: str | None = None,
    after_sha: str | None = None,
    include_summary: bool = False,
) -> AnalyzeInputs:
    """Normalize, validate, and resolve all ``analyze`` arguments.

    Raises :class:`ValueError` on constraint violations (e.g. ``after_sha``
    without ``before_sha``, or snapshot SHAs on a remote URL).
    """
    after_t = after_sha.strip() if isinstance(after_sha, str) else ""
    before_t = before_sha.strip() if isinstance(before_sha, str) else ""
    after_sha_clean: str | None = after_t or None
    before_sha_clean: str | None = before_t or None

    if after_sha_clean and not before_sha_clean:
        raise ValueError("after_sha requires before_sha")

    is_remote = discovery.is_git_url(target)

    if (before_sha_clean or after_sha_clean) and is_remote:
        raise ValueError(
            "before_sha and after_sha require a local git repository path, "
            "not a remote URL"
        )

    if is_remote:
        config_target = target.strip()
        analysis_root = config_target
        local_repo: Path | None = None
    else:
        config_target = str(resolve_local_repo_path(target))
        analysis_root = config_target
        local_repo = Path(config_target)

    cfg = build_analyze_config(
        config_target,
        path_filter=path_filter,
        score_metrics=score_metrics,
        granularity="block",
        limit=limit,
        directories=False,
        sort=sort,
        since=since,
        until=until,
        respect_gitignore=respect_gitignore,
        ignore_dir=ignore_dir,
        config_overrides=config_overrides,
    )
    cfg["similarity_enabled"] = effective_similarity_enabled_for_mcp_analyze(
        similarity, path_filter
    )

    return AnalyzeInputs(
        analysis_root=analysis_root,
        local_repo=local_repo,
        cfg=cfg,
        before_sha=before_sha_clean,
        after_sha=after_sha_clean,
        compact=compact,
        include_summary=include_summary,
    )
