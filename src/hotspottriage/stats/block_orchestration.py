"""Orchestrate multi-pass block analysis: scan, churn, assemble, score, persist."""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, Iterable

from hotspottriage import block_churn as _block_churn
from hotspottriage import block_similarity as _block_similarity
from hotspottriage import cache as _cache
from hotspottriage.statistic_row import Statistic

from hotspottriage.stats.block_assembly import assemble_block_metrics
from hotspottriage.stats.block_build import build_block_statistics_rows
from hotspottriage.stats.block_cache_io import load_previous_cache, persist_block_cache
from hotspottriage.stats.block_churn_pass import compute_block_churns
from hotspottriage.stats.block_context import BlockAnalysisContext
from hotspottriage.stats.block_scan import scan_files_for_blocks
from hotspottriage.stats.risk_application import apply_risk_scores
from hotspottriage.stats.similarity_row import similarity_aggregate_statistic
from hotspottriage.stats.smell_burden import finalize_smell_burden

logger = logging.getLogger(__name__)


def build_block_stats(
    repo: Path,
    files: Iterable[str],
    score_metrics: Iterable[str],
    since: str | None = None,
    until: str | None = None,
    workers: int | None = None,
    decay_half_life: int | None = None,
    smell_weight: float = 0.0,
    progress_callback: Callable[[str, int, int], None] | None = None,
    merged_config: dict[str, Any] | None = None,
    *,
    cache_manager: _cache.BlockCacheManager | None = None,
    similarity_enabled: bool = True,
    similarity_threshold: float = 80.0,
    similarity_band_high: float = 85.0,
    similarity_band_medium: float = 70.0,
    similarity_band_low: float = 50.0,
    similarity_max_pairwise_blocks: int = 2500,
    similarity_aggregate_row: bool = True,
) -> list[Statistic]:
    """One Statistic per function/method (no class rows).

    Maintainability is inherited from the file. Churn is computed via
    ``git log -L`` per block, cached on disk by file blob SHA.
    """
    from hotspottriage import churn as _churn
    from datetime import datetime

    sm = list(score_metrics)
    files_list = list(files)
    cfg = merged_config if merged_config is not None else {}

    previous_rows, prev_rows_list = load_previous_cache(repo, cache_manager)
    ctx = BlockAnalysisContext(
        repo=repo,
        files=files_list,
        blob_shas=_block_churn.file_blob_shas(repo),
        previous_rows=previous_rows,
        prev_rows_list=prev_rows_list,
        timestamps=_churn.get_file_timestamps(repo, files_list),
        current_time=int(datetime.now().timestamp()),
        merged_config=cfg,
    )

    file_metrics, file_blocks, file_sources, file_smells, requests = scan_files_for_blocks(
        ctx, progress_callback
    )
    churns = compute_block_churns(ctx, requests, since, until, workers, progress_callback)
    rows, row_cache_meta = assemble_block_metrics(
        ctx, file_metrics, file_blocks, file_sources, file_smells, churns, decay_half_life
    )

    finalize_smell_burden([m for _, _, m in rows])

    sim_agg = _block_similarity.attach_similarity_to_rows(
        rows,
        file_sources,
        similarity_enabled=similarity_enabled,
        similarity_threshold=similarity_threshold,
        similarity_band_high=similarity_band_high,
        similarity_band_medium=similarity_band_medium,
        similarity_band_low=similarity_band_low,
        similarity_max_pairwise_blocks=similarity_max_pairwise_blocks,
    )

    out = build_block_statistics_rows(rows, sm, smell_weight, progress_callback)
    apply_risk_scores(out, cfg, similarity_enabled)

    if (
        similarity_enabled
        and similarity_aggregate_row
        and sim_agg is not None
        and int(sim_agg.get("blocks_total") or 0) > 0
    ):
        out.append(similarity_aggregate_statistic(sim_agg))

    try:
        persist_block_cache(out, row_cache_meta, files_list, repo, cache_manager, prev_rows_list)
    except Exception:
        logger.debug("Persisting block cache after analysis skipped", exc_info=True)

    return out
