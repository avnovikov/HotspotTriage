"""Compare block-level statistics between two revision row lists (MCP ``deltas``)."""
from __future__ import annotations

from typing import Any

from hotspottriage import stats
from hotspottriage.mcp.block_row_utils import (
    is_block_row_for_delta,
    metric_triplet,
    rows_equal_raw,
)


def build_block_delta_report(
    head_rows: list[stats.Statistic],
    base_rows: list[stats.Statistic],
) -> dict[str, Any]:
    """Compare block rows at HEAD vs a baseline revision (raw metrics + score snapshot)."""
    head_map = {r.path: r for r in head_rows if is_block_row_for_delta(r)}
    base_map = {r.path: r for r in base_rows if is_block_row_for_delta(r)}
    all_paths = sorted(set(head_map) | set(base_map))
    by_block: list[dict[str, Any]] = []
    blocks_added = blocks_removed = blocks_modified = blocks_unchanged = 0
    total_cyclomatic_delta = 0
    total_sloc_delta = 0
    total_halstead_delta = 0
    total_churn_delta = 0
    total_smell_count_delta = 0

    for path in all_paths:
        h = head_map.get(path)
        b = base_map.get(path)
        if h and b:
            if rows_equal_raw(h, b):
                blocks_unchanged += 1
                continue
            blocks_modified += 1
            status = "modified"
        elif h and not b:
            blocks_added += 1
            status = "added"
        else:
            blocks_removed += 1
            status = "removed"
            assert b is not None

        entry: dict[str, Any] = {"path": path, "status": status}
        for fname in ("cyclomatic", "sloc", "halstead", "churn", "smell_count"):
            bv = int(getattr(b, fname)) if b else None
            hv = int(getattr(h, fname)) if h else None
            entry[fname] = metric_triplet(bv, hv)
        for fname in ("churn_per_sloc", "decayed_churn", "decayed_churn_per_sloc"):
            bv = float(getattr(b, fname)) if b else None
            hv = float(getattr(h, fname)) if h else None
            entry[fname] = metric_triplet(bv, hv)
        entry["score"] = metric_triplet(
            float(b.score) if b else None,
            float(h.score) if h else None,
        )
        by_block.append(entry)

        if status == "modified" and h and b:
            total_cyclomatic_delta += h.cyclomatic - b.cyclomatic
            total_sloc_delta += h.sloc - b.sloc
            total_halstead_delta += h.halstead - b.halstead
            total_churn_delta += h.churn - b.churn
            total_smell_count_delta += h.smell_count - b.smell_count
        elif status == "added" and h:
            total_cyclomatic_delta += h.cyclomatic
            total_sloc_delta += h.sloc
            total_halstead_delta += h.halstead
            total_churn_delta += h.churn
            total_smell_count_delta += h.smell_count
        elif status == "removed" and b:
            total_cyclomatic_delta -= b.cyclomatic
            total_sloc_delta -= b.sloc
            total_halstead_delta -= b.halstead
            total_churn_delta -= b.churn
            total_smell_count_delta -= b.smell_count

    return {
        "summary": {
            "blocks_added": blocks_added,
            "blocks_removed": blocks_removed,
            "blocks_modified": blocks_modified,
            "blocks_unchanged": blocks_unchanged,
            "total_cyclomatic_delta": total_cyclomatic_delta,
            "total_sloc_delta": total_sloc_delta,
            "total_halstead_delta": total_halstead_delta,
            "total_churn_delta": total_churn_delta,
            "total_smell_count_delta": total_smell_count_delta,
        },
        "by_block": by_block,
    }
