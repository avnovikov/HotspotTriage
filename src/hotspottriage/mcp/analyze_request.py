"""Typed MCP ``analyze`` / cache-backed block analysis request (value object)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AnalyzeRequest:
    """Parameters for a single cache-backed block analysis (before JSON wrapping)."""

    target: str
    path_filter: str | None = None
    score_metrics: str | None = None
    limit: int | None = None
    since: str | None = None
    until: str | None = None
    respect_gitignore: bool = True
    ignore_dir: str | None = None
    similarity: bool | None = None
    compact: bool = True
    sort: str = "score"
    config_overrides: dict[str, Any] | None = None
    before_sha: str | None = None
    after_sha: str | None = None
    include_summary: bool = False
    progress_callback: Callable[[str, int, int], None] | None = None

    @classmethod
    def from_tool_kwargs(
        cls,
        target: str,
        *,
        filter: str | None = None,
        score_metrics: str | None = None,
        limit: int | None = None,
        since: str | None = None,
        until: str | None = None,
        respect_gitignore: bool = True,
        ignore_dir: str | None = None,
        similarity: bool | None = None,
        compact: bool = True,
        sort: str = "score",
        progress_callback: Callable[[str, int, int], None] | None = None,
        config_overrides: dict[str, Any] | None = None,
        before_sha: str | None = None,
        after_sha: str | None = None,
        include_summary: bool = False,
    ) -> AnalyzeRequest:
        """Build from ``run_cached_block_analysis_dict`` / ``analyze`` keyword args."""
        return cls(
            target=target,
            path_filter=filter,
            score_metrics=score_metrics,
            limit=limit,
            since=since,
            until=until,
            respect_gitignore=respect_gitignore,
            ignore_dir=ignore_dir,
            similarity=similarity,
            compact=compact,
            sort=sort,
            progress_callback=progress_callback,
            config_overrides=config_overrides,
            before_sha=before_sha,
            after_sha=after_sha,
            include_summary=include_summary,
        )
