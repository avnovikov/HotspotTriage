"""Compare block-level statistics between two revision row lists (MCP ``deltas``)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from hotspottriage import stats
from hotspottriage.mcp.block_row_utils import (
    is_block_row_for_delta,
    metric_triplet,
    rows_equal_raw,
)

_IntMetric = Literal["cyclomatic", "sloc", "halstead", "churn", "smell_count"]
_FloatMetric = Literal["churn_per_sloc", "decayed_churn", "decayed_churn_per_sloc"]

_INT_METRICS: tuple[_IntMetric, ...] = (
    "cyclomatic",
    "sloc",
    "halstead",
    "churn",
    "smell_count",
)
_FLOAT_METRICS: tuple[_FloatMetric, ...] = (
    "churn_per_sloc",
    "decayed_churn",
    "decayed_churn_per_sloc",
)


def _row_maps(
    head_rows: list[stats.Statistic], base_rows: list[stats.Statistic]
) -> tuple[dict[str, stats.Statistic], dict[str, stats.Statistic]]:
    head_map = {r.path: r for r in head_rows if is_block_row_for_delta(r)}
    base_map = {r.path: r for r in base_rows if is_block_row_for_delta(r)}
    return head_map, base_map


def _classify_pair(
    h: stats.Statistic | None, b: stats.Statistic | None
) -> tuple[Literal["unchanged"], None, None] | tuple[str, stats.Statistic | None, stats.Statistic | None]:
    """Return ``(\"unchanged\", None, None)`` or ``(status, h, b)`` for a delta row."""
    if h is not None and b is not None:
        if rows_equal_raw(h, b):
            return "unchanged", None, None
        return "modified", h, b
    if h is not None and b is None:
        return "added", h, None
    assert b is not None
    return "removed", None, b


def _by_block_entry(
    path: str,
    h: stats.Statistic | None,
    b: stats.Statistic | None,
    status: str,
) -> dict[str, Any]:
    entry: dict[str, Any] = {"path": path, "status": status}
    for fname in _INT_METRICS:
        bv = int(getattr(b, fname)) if b else None
        hv = int(getattr(h, fname)) if h else None
        entry[fname] = metric_triplet(bv, hv)
    for fname in _FLOAT_METRICS:
        bv = float(getattr(b, fname)) if b else None
        hv = float(getattr(h, fname)) if h else None
        entry[fname] = metric_triplet(bv, hv)
    entry["score"] = metric_triplet(
        float(b.score) if b else None,
        float(h.score) if h else None,
    )
    return entry


@dataclass
class _DeltaSummaryCounters:
    blocks_added: int = 0
    blocks_removed: int = 0
    blocks_modified: int = 0
    blocks_unchanged: int = 0
    total_cyclomatic_delta: int = 0
    total_sloc_delta: int = 0
    total_halstead_delta: int = 0
    total_churn_delta: int = 0
    total_smell_count_delta: int = 0

    def add_modified(self, h: stats.Statistic, b: stats.Statistic) -> None:
        self.blocks_modified += 1
        self.total_cyclomatic_delta += h.cyclomatic - b.cyclomatic
        self.total_sloc_delta += h.sloc - b.sloc
        self.total_halstead_delta += h.halstead - b.halstead
        self.total_churn_delta += h.churn - b.churn
        self.total_smell_count_delta += h.smell_count - b.smell_count

    def add_added(self, h: stats.Statistic) -> None:
        self.blocks_added += 1
        self.total_cyclomatic_delta += h.cyclomatic
        self.total_sloc_delta += h.sloc
        self.total_halstead_delta += h.halstead
        self.total_churn_delta += h.churn
        self.total_smell_count_delta += h.smell_count

    def add_removed(self, b: stats.Statistic) -> None:
        self.blocks_removed += 1
        self.total_cyclomatic_delta -= b.cyclomatic
        self.total_sloc_delta -= b.sloc
        self.total_halstead_delta -= b.halstead
        self.total_churn_delta -= b.churn
        self.total_smell_count_delta -= b.smell_count

    def record(self, status: str, h: stats.Statistic | None, b: stats.Statistic | None) -> None:
        if status == "modified" and h is not None and b is not None:
            self.add_modified(h, b)
        elif status == "added" and h is not None:
            self.add_added(h)
        elif status == "removed" and b is not None:
            self.add_removed(b)


def build_block_delta_report(
    head_rows: list[stats.Statistic],
    base_rows: list[stats.Statistic],
) -> dict[str, Any]:
    """Compare block rows at HEAD vs a baseline revision (raw metrics + score snapshot)."""
    head_map, base_map = _row_maps(head_rows, base_rows)
    all_paths = sorted(set(head_map) | set(base_map))
    by_block: list[dict[str, Any]] = []
    counters = _DeltaSummaryCounters()

    for path in all_paths:
        h = head_map.get(path)
        b = base_map.get(path)
        status, rh, rb = _classify_pair(h, b)
        if status == "unchanged":
            counters.blocks_unchanged += 1
            continue
        counters.record(status, rh, rb)
        by_block.append(_by_block_entry(path, rh, rb, status))

    return {
        "summary": {
            "blocks_added": counters.blocks_added,
            "blocks_removed": counters.blocks_removed,
            "blocks_modified": counters.blocks_modified,
            "blocks_unchanged": counters.blocks_unchanged,
            "total_cyclomatic_delta": counters.total_cyclomatic_delta,
            "total_sloc_delta": counters.total_sloc_delta,
            "total_halstead_delta": counters.total_halstead_delta,
            "total_churn_delta": counters.total_churn_delta,
            "total_smell_count_delta": counters.total_smell_count_delta,
        },
        "by_block": by_block,
    }
