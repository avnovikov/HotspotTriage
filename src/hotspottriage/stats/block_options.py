"""Grouped parameters for block- and file-level stats (reduces long-parameter-list churn)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hotspottriage import blocks as _blocks
from hotspottriage import cache as _cache
from hotspottriage.statistic_row import Statistic
from hotspottriage.stats.similarity_row import block_similarity_kwargs_from_config


@dataclass(frozen=True, slots=True)
class BlockChurnWindow:
    """Git time range, worker pool, and decay for block churn."""

    since: str | None = None
    until: str | None = None
    workers: int | None = None
    decay_half_life: int | None = None


@dataclass(frozen=True, slots=True)
class BlockStatsRuntime:
    """Callbacks, merged config, cache manager, and smell weight for a block run."""

    smell_weight: float = 0.0
    progress_callback: Callable[[str, int, int], None] | None = None
    merged_config: dict[str, Any] | None = None
    cache_manager: _cache.BlockCacheManager | None = None


@dataclass(frozen=True, slots=True)
class BlockSimilarityConfig:
    """DeepCSIM integration flags (mirrors ``block_similarity_kwargs_from_config`` keys)."""

    enabled: bool = True
    threshold: float = 80.0
    band_high: float = 85.0
    band_medium: float = 70.0
    band_low: float = 50.0
    max_pairwise_blocks: int = 2500
    aggregate_row: bool = True

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> BlockSimilarityConfig:
        d = block_similarity_kwargs_from_config(cfg)
        return cls(
            enabled=bool(d["similarity_enabled"]),
            threshold=float(d["similarity_threshold"]),
            band_high=float(d["similarity_band_high"]),
            band_medium=float(d["similarity_band_medium"]),
            band_low=float(d["similarity_band_low"]),
            max_pairwise_blocks=int(d["similarity_max_pairwise_blocks"]),
            aggregate_row=bool(d["similarity_aggregate_row"]),
        )

    def attach_similarity_kwargs(self) -> dict[str, Any]:
        return {
            "similarity_enabled": self.enabled,
            "similarity_threshold": self.threshold,
            "similarity_band_high": self.band_high,
            "similarity_band_medium": self.band_medium,
            "similarity_band_low": self.band_low,
            "similarity_max_pairwise_blocks": self.max_pairwise_blocks,
        }


@dataclass(frozen=True, slots=True)
class BlockAssemblyInputs:
    """Outputs of scan + churn passes fed into metric assembly."""

    file_metrics: dict[str, dict[str, int]]
    file_blocks: dict[str, list[_blocks.Block]]
    file_sources: dict[str, str]
    file_smells: dict[str, list[dict[str, Any]]]
    churns: dict[tuple[str, int, int], int]


@dataclass(frozen=True, slots=True)
class ChurnComputeSpec:
    """Arguments for the parallel ``git log -L`` churn pass."""

    since: str | None = None
    until: str | None = None
    workers: int | None = None
    progress_callback: Callable[[str, int, int], None] | None = None


@dataclass(frozen=True, slots=True)
class BlockPersistPayload:
    """Everything needed to merge new block rows into the on-disk cache."""

    out: list[Statistic]
    row_cache_meta: list[dict[str, str | int]]
    files: list[str]
    repo: Path
    cache_manager: _cache.BlockCacheManager | None
    prev_rows_list: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class FileStatsRun:
    """Optional knobs for :func:`build_stats` beyond the four core arguments."""

    decay_half_life: int | None = None
    smell_weight: float = 0.0
    progress_callback: Callable[[str, int, int], None] | None = None
    merged_config: dict[str, Any] | None = None
