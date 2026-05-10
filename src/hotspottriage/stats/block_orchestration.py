"""Orchestrate multi-pass block analysis: scan, churn, assemble, score, persist."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterable

from hotspottriage import block_churn as _block_churn
from hotspottriage import block_similarity as _block_similarity
from hotspottriage.statistic_row import Statistic

from hotspottriage.stats.block_assembly import assemble_block_metrics
from hotspottriage.stats.block_build import build_block_statistics_rows
from hotspottriage.stats.block_cache_io import load_previous_cache, persist_block_cache
from hotspottriage.stats.block_churn_pass import compute_block_churns
from hotspottriage.stats.block_context import BlockAnalysisContext
from hotspottriage.stats.block_options import (
    BlockAssemblyInputs,
    BlockChurnWindow,
    BlockPersistPayload,
    BlockSimilarityConfig,
    BlockStatsRuntime,
    ChurnComputeSpec,
)
from hotspottriage.stats.block_scan import scan_files_for_blocks
from hotspottriage.stats.risk_application import apply_risk_scores
from hotspottriage.stats.similarity_row import similarity_aggregate_statistic
from hotspottriage.stats.smell_burden import finalize_smell_burden

logger = logging.getLogger(__name__)


def build_block_stats(
    repo: Path,
    files: Iterable[str],
    score_metrics: Iterable[str],
    *,
    churn: BlockChurnWindow | None = None,
    runtime: BlockStatsRuntime | None = None,
    similarity: BlockSimilarityConfig | None = None,
) -> list[Statistic]:
    """One Statistic per function/method (no class rows).

    Maintainability is inherited from the file. Churn is computed via
    ``git log -L`` per block, cached on disk by file blob SHA.
    """
    from hotspottriage import churn as _churn
    from datetime import datetime

    c = churn or BlockChurnWindow()
    rt = runtime or BlockStatsRuntime()
    sim = similarity or BlockSimilarityConfig()

    sm = list(score_metrics)
    files_list = list(files)
    cfg = rt.merged_config if rt.merged_config is not None else {}

    previous_rows, prev_rows_list = load_previous_cache(repo, rt.cache_manager)
    ctx = BlockAnalysisContext(
        repo=repo,
        files=files_list,
        blob_shas=_block_churn.file_blob_shas(repo),
        previous_rows=previous_rows,
        prev_rows_list=prev_rows_list,
        timestamps=_churn.get_file_timestamps(repo, files_list),
        current_time=int(datetime.now().timestamp()),
        merged_config=cfg,
        decay_half_life=c.decay_half_life,
    )

    file_metrics, file_blocks, file_sources, file_smells, requests = scan_files_for_blocks(
        ctx, rt.progress_callback
    )
    churns = compute_block_churns(
        ctx,
        requests,
        ChurnComputeSpec(
            since=c.since,
            until=c.until,
            workers=c.workers,
            progress_callback=rt.progress_callback,
        ),
    )
    assembly = BlockAssemblyInputs(
        file_metrics=file_metrics,
        file_blocks=file_blocks,
        file_sources=file_sources,
        file_smells=file_smells,
        churns=churns,
    )
    rows, row_cache_meta = assemble_block_metrics(ctx, assembly)

    finalize_smell_burden([m for _, _, m in rows])

    sim_agg = _block_similarity.attach_similarity_to_rows(
        rows,
        file_sources,
        **sim.attach_similarity_kwargs(),
    )

    out = build_block_statistics_rows(rows, sm, rt.smell_weight, rt.progress_callback)
    apply_risk_scores(out, cfg, sim.enabled)

    if (
        sim.enabled
        and sim.aggregate_row
        and sim_agg is not None
        and int(sim_agg.get("blocks_total") or 0) > 0
    ):
        out.append(similarity_aggregate_statistic(sim_agg))

    try:
        persist_block_cache(
            BlockPersistPayload(
                out=out,
                row_cache_meta=row_cache_meta,
                files=files_list,
                repo=repo,
                cache_manager=rt.cache_manager,
                prev_rows_list=prev_rows_list,
            )
        )
    except Exception:
        logger.debug("Persisting block cache after analysis skipped", exc_info=True)

    return out
