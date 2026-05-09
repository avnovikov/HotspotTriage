"""Orchestrate block-level analysis: cache partition, stale pipeline, merge, persist."""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, Iterable

from hotspottriage import block_similarity as _block_similarity
from hotspottriage import blocks as _blocks
from hotspottriage import cache as _cache
from hotspottriage import churn as _churn
from hotspottriage.statistic_row import Statistic

from hotspottriage.stats import cache_ops
from hotspottriage.stats import core
from hotspottriage.stats import pipeline
from hotspottriage.stats import scoring
from hotspottriage.stats.pipeline import _BlockAnalysisContext

logger = logging.getLogger(__name__)


def _prepare_block_context(
    repo: Path,
    files_list: list[str],
    cfg: dict[str, Any],
    cache_manager: _cache.BlockCacheManager | None,
    get_file_timestamps: Callable[[Path, list[str]], dict[str, int]],
) -> tuple[
    _BlockAnalysisContext,
    set[str],
    list[str],
    dict[str, str],
    list[dict[str, Any]],
]:
    """Load cache, partition files, and build context for block analysis."""
    from datetime import datetime

    from hotspottriage import block_churn as _block_churn

    previous_rows, prev_rows_list = cache_ops._load_previous_cache(repo, cache_manager)
    blob_shas = _block_churn.file_blob_shas(repo)
    cached_files, file_sources = cache_ops._partition_complete_block_cache_files(
        files_list, blob_shas, previous_rows, repo
    )
    cached_set = set(cached_files)
    stale_files = [f for f in files_list if f not in cached_set]

    ctx = _BlockAnalysisContext(
        repo=repo,
        files=stale_files,
        blob_shas=blob_shas,
        previous_rows=previous_rows,
        prev_rows_list=prev_rows_list,
        timestamps=get_file_timestamps(repo, files_list),
        current_time=int(datetime.now().timestamp()),
        merged_config=cfg,
    )
    return ctx, cached_set, stale_files, file_sources, prev_rows_list


def _merge_and_attach_similarity(
    files_list: list[str],
    cached_set: set[str],
    cached_tagged: list[tuple[str, _blocks.Block, dict[str, Any], None]],
    stale_rows: list[tuple[str, _blocks.Block, dict[str, Any]]],
    stale_row_cache_meta: list[dict[str, str | int]],
    file_sources: dict[str, str],
    *,
    similarity_enabled: bool,
    similarity_threshold: float,
    similarity_band_high: float,
    similarity_band_medium: float,
    similarity_band_low: float,
    similarity_max_pairwise_blocks: int,
) -> tuple[
    list[tuple[str, _blocks.Block, dict[str, Any], dict[str, str | int] | None]],
    dict[str, Any] | None,
]:
    """Merge cached + stale tagged rows, finalize smells, attach similarity."""
    stale_tagged = [
        (rel, b, m, meta)
        for (rel, b, m), meta in zip(stale_rows, stale_row_cache_meta, strict=True)
    ]
    merged_tagged = cache_ops._merge_tagged_block_rows_by_file_order(
        files_list, cached_set, cached_tagged, stale_tagged
    )
    merged_rows = [(rel, b, m) for rel, b, m, _meta in merged_tagged]

    core._finalize_smell_burden([m for _, _, m in merged_rows])

    sim_agg = _block_similarity.attach_similarity_to_rows(
        merged_rows,
        file_sources,
        similarity_enabled=similarity_enabled,
        similarity_threshold=similarity_threshold,
        similarity_band_high=similarity_band_high,
        similarity_band_medium=similarity_band_medium,
        similarity_band_low=similarity_band_low,
        similarity_max_pairwise_blocks=similarity_max_pairwise_blocks,
    )
    return merged_tagged, sim_agg


def _build_scored_statistics(
    merged_tagged: list[
        tuple[str, _blocks.Block, dict[str, Any], dict[str, str | int] | None]
    ],
    sm: list[str],
    *,
    smell_weight: float,
    cfg: dict[str, Any],
    similarity_enabled: bool,
    progress_callback: Callable[[str, int, int], None] | None,
) -> tuple[list[Statistic], list[Statistic], list[dict[str, str | int]]]:
    """Score each merged row and separate persist-worthy (stale) entries."""
    normalized_slocs = core._normalize_sloc([int(m["sloc"]) for _, _, m, _ in merged_tagged])
    out: list[Statistic] = []
    persist_stats: list[Statistic] = []
    persist_meta: list[dict[str, str | int]] = []
    total_rows = len(merged_tagged)

    if progress_callback:
        progress_callback("Building block rows", 0, total_rows)

    for i, ((rel, b, m, meta), norm_sloc) in enumerate(
        zip(merged_tagged, normalized_slocs, strict=True), start=1
    ):
        row_dict: dict[str, Any] = dict(m)
        row_dict["path"] = f"{rel}::{b.name}"
        row_dict["normalized_sloc"] = norm_sloc
        st = scoring.statistic_from_raw_block_row(
            row_dict,
            sm,
            smell_weight=smell_weight,
            merged_config=cfg,
            similarity_enabled=similarity_enabled,
        )
        out.append(st)
        if meta is not None:
            persist_stats.append(st)
            persist_meta.append(meta)
        if progress_callback:
            progress_callback(f"{rel}::{b.name}", i, total_rows)

    return out, persist_stats, persist_meta


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
    `git log -L` per block, cached on disk by file blob SHA.
    """
    sm = list(score_metrics)
    files_list = list(files)
    cfg = merged_config if merged_config is not None else {}

    ctx, cached_set, stale_files, file_sources, prev_rows_list = _prepare_block_context(
        repo, files_list, cfg, cache_manager, _churn.get_file_timestamps,
    )

    outer_scan_total = sum(1 for f in files_list if f in ctx.blob_shas)
    cached_scan_count = sum(1 for f in files_list if f in ctx.blob_shas and f in cached_set)

    if progress_callback and outer_scan_total > 0:
        for i, rel in enumerate(f for f in files_list if f in ctx.blob_shas and f in cached_set):
            progress_callback(f"Scanning {rel}", i, outer_scan_total)

    stale_rows, stale_row_cache_meta = pipeline._run_stale_pipeline(
        ctx,
        file_sources,
        since=since,
        until=until,
        workers=workers,
        decay_half_life=decay_half_life,
        cached_scan_count=cached_scan_count,
        outer_scan_total=outer_scan_total,
        progress_callback=progress_callback,
    )

    cached_tagged = cache_ops._cached_block_rows_tagged(
        files_list, cached_set, file_sources, ctx.previous_rows
    )
    merged_tagged, sim_agg = _merge_and_attach_similarity(
        files_list,
        cached_set,
        cached_tagged,
        stale_rows,
        stale_row_cache_meta,
        file_sources,
        similarity_enabled=similarity_enabled,
        similarity_threshold=similarity_threshold,
        similarity_band_high=similarity_band_high,
        similarity_band_medium=similarity_band_medium,
        similarity_band_low=similarity_band_low,
        similarity_max_pairwise_blocks=similarity_max_pairwise_blocks,
    )

    out, persist_stats, persist_meta = _build_scored_statistics(
        merged_tagged,
        sm,
        smell_weight=smell_weight,
        cfg=cfg,
        similarity_enabled=similarity_enabled,
        progress_callback=progress_callback,
    )

    if (
        similarity_enabled
        and similarity_aggregate_row
        and sim_agg is not None
        and int(sim_agg.get("blocks_total") or 0) > 0
    ):
        out.append(core._similarity_aggregate_statistic(sim_agg))

    try:
        cache_ops._persist_block_cache(
            persist_stats, persist_meta, stale_files, repo, cache_manager, prev_rows_list
        )
    except Exception:
        logger.debug("Persisting block cache after analysis skipped", exc_info=True)

    return out
