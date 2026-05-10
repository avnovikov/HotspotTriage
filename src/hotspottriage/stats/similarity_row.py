"""DeepCSIM aggregate row and config kwargs for block stats."""
from __future__ import annotations

from typing import Any

from hotspottriage.statistic_row import Statistic


def block_similarity_kwargs_from_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Keyword arguments for :func:`build_block_stats` DeepCSIM integration."""
    return {
        "similarity_enabled": bool(cfg.get("similarity_enabled", True)),
        "similarity_threshold": float(cfg.get("similarity_threshold", 80.0)),
        "similarity_band_high": float(cfg.get("similarity_band_high", 85.0)),
        "similarity_band_medium": float(cfg.get("similarity_band_medium", 70.0)),
        "similarity_band_low": float(cfg.get("similarity_band_low", 50.0)),
        "similarity_max_pairwise_blocks": int(
            cfg.get("similarity_max_pairwise_blocks", 2500)
        ),
        "similarity_aggregate_row": bool(cfg.get("similarity_aggregate_row", True)),
    }


def similarity_aggregate_statistic(agg: dict[str, Any]) -> Statistic:
    """Synthetic row with repo-wide DeepCSIM summary (``path`` is reserved)."""
    total_b = int(agg.get("blocks_total") or 0)
    mean_sim = float(agg.get("mean_similarity_score") or 0.0)
    usages = int(agg.get("total_match_usages") or 0)
    usable = int(agg.get("blocks_with_metrics") or 0)
    return Statistic(
        path="__aggregate_similarity__::repo",
        sloc=total_b,
        normalized_sloc=0.0,
        cyclomatic=usable,
        halstead=usages,
        maintainability=0,
        churn=0,
        churn_per_sloc=0.0,
        decayed_churn=0.0,
        decayed_churn_per_sloc=0.0,
        smell_count=0,
        smell_severity=0.0,
        smell_burden=0.0,
        smells={},
        similarity_score=mean_sim,
        similarity_band="aggregate",
        match_count=usages,
        score=mean_sim,
        score_band="aggregate",
        score_subscores={},
    )
