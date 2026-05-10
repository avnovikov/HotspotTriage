"""Full file- or block-level analysis pipeline for MCP (mirrors CLI flow)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from hotspottriage import cache as ht_cache
from hotspottriage import churn as ht_churn
from hotspottriage import config as ht_config
from hotspottriage import discovery, stats
from hotspottriage.mcp.repo_filter import build_repo_keep_predicate


def analyze_repository(
    target: str,
    cfg: dict[str, Any],
    *,
    get_cache_manager: Callable[[Path], ht_cache.BlockCacheManager],
    apply_limit: bool = True,
    progress_callback: Callable[[str, int, int], None] | None = None,
) -> list[stats.Statistic]:
    """Run analysis for *target* using *cfg*; same filtering and metrics as CLI."""
    ht_config.validate(cfg)
    with discovery.resolve_target(target) as repo:
        keep = build_repo_keep_predicate(repo, cfg)
        files = [f for f in discovery.list_tracked_files(repo) if keep(f)]
        score_metrics = list(cfg["score_metrics"])

        decay_half_life = cfg.get("decay_half_life")
        smell_weight = float(cfg.get("smell_weight", 0.0))
        mgr = get_cache_manager(repo)
        if cfg["granularity"] == "block":
            results = stats.build_block_stats(
                repo,
                files,
                score_metrics,
                churn=stats.BlockChurnWindow(
                    since=cfg["since"],
                    until=cfg["until"],
                    workers=cfg.get("block_workers"),
                    decay_half_life=decay_half_life,
                ),
                runtime=stats.BlockStatsRuntime(
                    smell_weight=smell_weight,
                    progress_callback=progress_callback,
                    merged_config=cfg,
                    cache_manager=mgr,
                ),
                similarity=stats.BlockSimilarityConfig.from_config(cfg),
            )
        else:
            churn = ht_churn.compute_churn(
                repo, since=cfg["since"], until=cfg["until"]
            )
            results = stats.build_stats(
                repo,
                files,
                churn,
                score_metrics,
                options=stats.FileStatsRun(
                    decay_half_life=decay_half_life,
                    smell_weight=smell_weight,
                    merged_config=cfg,
                ),
            )
            if cfg["directories"]:
                results = stats.aggregate_by_directory(
                    results, score_metrics, smell_weight=smell_weight
                )

        lim = cfg["limit"] if apply_limit else None
        return stats.sort_and_limit(results, by=cfg["sort"], limit=lim)
