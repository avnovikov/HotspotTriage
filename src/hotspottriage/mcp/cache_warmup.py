"""Warm block cache for a repo (MCP ``generate_cache`` path)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from hotspottriage import cache as ht_cache
from hotspottriage import config as ht_config
from hotspottriage import discovery, stats
from hotspottriage.mcp.repo_filter import build_repo_keep_predicate


def initialize_repository_cache(
    target: str,
    cfg: dict[str, Any],
    *,
    get_cache_manager: Callable[[Path], ht_cache.BlockCacheManager],
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> dict[str, Any]:
    """Build block-level cache for *target*; return ``block_cache_stats`` dict."""
    ht_config.validate(cfg)
    with discovery.resolve_target(target) as repo:
        keep = build_repo_keep_predicate(repo, cfg)
        files = [f for f in discovery.list_tracked_files(repo) if keep(f)]
        score_metrics = list(cfg["score_metrics"])

        mgr = get_cache_manager(repo)
        stats.build_block_stats(
            repo,
            files,
            score_metrics,
            since=cfg["since"],
            until=cfg["until"],
            workers=cfg.get("block_workers"),
            decay_half_life=cfg.get("decay_half_life"),
            smell_weight=float(cfg.get("smell_weight", 0.0)),
            progress_callback=progress_callback,
            merged_config=cfg,
            cache_manager=mgr,
            **stats.block_similarity_kwargs_from_config(cfg),
        )
        mgr.flush()

        return ht_cache.block_cache_stats(repo)
