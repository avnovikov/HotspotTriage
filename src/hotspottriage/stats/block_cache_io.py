"""Load and persist block cache rows (``blocks.pkl``)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from hotspottriage import cache as _cache
from hotspottriage.statistic_row import Statistic

DERIVED_BLOCK_CACHE_KEYS = frozenset(
    {
        "score",
        "score_band",
        "score_subscores",
        "score_driver",
        "score_explanation",
        "score_final_weights",
        "score_norm_inputs",
    }
)


def load_previous_cache(
    repo: Path, cache_manager: _cache.BlockCacheManager | None
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Load previous cache rows from manager or disk."""
    if cache_manager is not None:
        previous_rows = cache_manager.get_previous_rows_index()
        return previous_rows, list(previous_rows.values())
    prev_rows_list = _cache.load_block_results(repo) or []
    previous_rows = {
        r["path"]: r for r in prev_rows_list if isinstance(r, dict) and "path" in r
    }
    return previous_rows, prev_rows_list


def raw_block_cache_row(
    stat: Statistic,
    meta: dict[str, str | int],
) -> dict[str, Any]:
    """Return the raw persisted row for a block statistic."""
    row = stat.as_dict()
    for key in list(row):
        if key in DERIVED_BLOCK_CACHE_KEYS or key.startswith("norm_"):
            del row[key]
    row.update(meta)
    return row


def persist_block_cache(
    out: list[Statistic],
    row_cache_meta: list[dict[str, str | int]],
    files: list[str],
    repo: Path,
    cache_manager: _cache.BlockCacheManager | None,
    prev_rows_list: list[dict[str, Any]],
) -> None:
    """Persist results with cache metadata for next run's churn lookup."""
    cache_rows: list[dict[str, Any]] = []
    for stat, meta in zip(out, row_cache_meta):
        cache_rows.append(raw_block_cache_row(stat, meta))

    if not files:
        return

    targeted_files = set(files)
    if cache_manager is not None:
        cache_manager.put_rows(cache_rows, targeted_files=targeted_files)
    else:
        preserved: list[dict[str, Any]] = []
        for row in prev_rows_list:
            if not isinstance(row, dict):
                continue
            path = str(row.get("path", ""))
            if "::" not in path:
                continue
            rel, _ = path.split("::", 1)
            if rel not in targeted_files:
                preserved.append(row)
        _cache.save_block_results(repo, [*preserved, *cache_rows])
