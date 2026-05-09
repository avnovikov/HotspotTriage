"""Statistic aggregation, file-level and block-level analysis, and cache integration.

Implementation is split across submodules (:mod:`hotspottriage.stats.core`,
:mod:`hotspottriage.stats.cache_ops`, :mod:`hotspottriage.stats.pipeline`,
:mod:`hotspottriage.stats.scoring`, :mod:`hotspottriage.stats.orchestration`).
"""
from __future__ import annotations

from hotspottriage.statistic_row import Statistic

from hotspottriage.stats._constants import BLOCK_CACHE_META_KEYS, DERIVED_BLOCK_CACHE_KEYS
from hotspottriage.stats.cache_ops import (
    _cached_block_rows_tagged,
    _load_previous_cache,
    _merge_tagged_block_rows_by_file_order,
    _metrics_dict_from_cached_row,
    _partition_complete_block_cache_files,
    _persist_block_cache,
    _raw_block_cache_row,
)
from hotspottriage.stats.core import (
    _decayed_value,
    _finalize_smell_burden,
    _normalize_sloc,
    _ratio,
    _score,
    _similarity_aggregate_statistic,
    aggregate_by_directory,
    block_similarity_kwargs_from_config,
    build_stats,
    sort_and_limit,
)
from hotspottriage.stats.orchestration import build_block_stats
from hotspottriage.stats.pipeline import (
    _BlockAnalysisContext,
    _assemble_block_metrics,
    _compute_block_churns,
    _process_single_file,
    _scan_files_for_blocks,
)
from hotspottriage.stats.scoring import (
    derive_block_score_rows,
    derive_block_statistics,
    statistic_from_complete_dict,
    statistic_from_raw_block_row,
)

__all__ = [
    "BLOCK_CACHE_META_KEYS",
    "DERIVED_BLOCK_CACHE_KEYS",
    "Statistic",
    "aggregate_by_directory",
    "block_similarity_kwargs_from_config",
    "build_block_stats",
    "build_stats",
    "derive_block_score_rows",
    "derive_block_statistics",
    "sort_and_limit",
    "statistic_from_complete_dict",
    "statistic_from_raw_block_row",
    "_BlockAnalysisContext",
    "_assemble_block_metrics",
    "_cached_block_rows_tagged",
    "_compute_block_churns",
    "_decayed_value",
    "_finalize_smell_burden",
    "_load_previous_cache",
    "_merge_tagged_block_rows_by_file_order",
    "_metrics_dict_from_cached_row",
    "_normalize_sloc",
    "_partition_complete_block_cache_files",
    "_persist_block_cache",
    "_process_single_file",
    "_raw_block_cache_row",
    "_ratio",
    "_scan_files_for_blocks",
    "_score",
    "_similarity_aggregate_statistic",
]
