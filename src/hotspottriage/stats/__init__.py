"""Statistic dataclass + aggregation, sorting, limiting.

Every Statistic carries every metric so a single CSV/JSON dump can be re-sorted
later without rerunning. For **file** rows, ``score`` is the product of
``score_metrics`` (``-s`` on the CLI). For **block** rows, when
``score_aggregation.enabled`` is true (default), ``score`` is the configured
0–1 risk aggregate from :mod:`hotspottriage.score`; otherwise the product recipe
applies. ``score_band`` and ``score_subscores`` are set for block aggregated runs.

`churn_per_sloc` is derived as ``churn / max(sloc, min_sloc_for_ratio)`` when
``sloc > 0`` (see ``min_sloc_for_ratio`` in config), so tiny files do not explode
per-line churn; instability is still normalized by size for larger blocks.

Implementation is split under :mod:`hotspottriage.stats` submodules; this
``__init__`` re-exports the stable public API.
"""
from __future__ import annotations

from hotspottriage.statistic_row import Statistic

from hotspottriage.stats.block_orchestration import build_block_stats
from hotspottriage.stats.directory_aggregate import aggregate_by_directory
from hotspottriage.stats.file_stats import build_stats
from hotspottriage.stats.from_cache import (
    derive_block_score_rows,
    derive_block_statistics,
    statistic_from_complete_dict,
    statistic_from_raw_block_row,
)
from hotspottriage.stats.metrics import decayed_value as _decayed_value
from hotspottriage.stats.metrics import ratio as _ratio
from hotspottriage.stats.similarity_row import block_similarity_kwargs_from_config
from hotspottriage.stats.sort_limit import sort_and_limit

__all__ = [
    "Statistic",
    "_decayed_value",
    "_ratio",
    "aggregate_by_directory",
    "block_similarity_kwargs_from_config",
    "build_block_stats",
    "build_stats",
    "derive_block_score_rows",
    "derive_block_statistics",
    "sort_and_limit",
    "statistic_from_complete_dict",
    "statistic_from_raw_block_row",
]
